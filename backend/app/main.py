"""FastAPI entrypoint.

Endpoints:
  GET  /healthz          -> liveness check
  POST /run-now          -> trigger the morning brief immediately (background task)
  GET  /history          -> list past runs (newest first)
  GET  /history/{id}     -> fetch a specific brief by run id
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import desc, select

import yaml

from .config import BACKEND_ROOT, get_settings
from .db import init_db, session_scope
from .models import AppSetting, Brief, Reminder, Run, YoutubeChannel
from .routers.reauth import router as reauth_router
from .routers.whatsapp import router as whatsapp_router
from .scheduler import start_scheduler, stop_scheduler
from .telegram_poller import start_poller, stop_poller
from .workflow import run_morning_brief

logger = logging.getLogger(__name__)
settings = get_settings()


def _seed_defaults() -> None:
    """Insert default app settings and migrate channels.yaml on first boot."""
    with session_scope() as s:
        # Feature flags — only insert if not already present
        for key, default in [("gmail_enabled", "true"), ("youtube_enabled", "true")]:
            if not s.get(AppSetting, key):
                s.add(AppSetting(key=key, value=default))

        # Migrate channels.yaml → youtube_channels table (one-time)
        existing_count = s.execute(
            select(YoutubeChannel)
        ).scalars().first()
        if existing_count is None:
            channels_file = BACKEND_ROOT / "config" / "channels.yaml"
            if channels_file.exists():
                data = yaml.safe_load(channels_file.read_text()) or {}
                for handle in data.get("channels") or []:
                    handle = handle.strip()
                    if handle:
                        s.add(YoutubeChannel(handle=handle))
                logger.info("Migrated channels.yaml → youtube_channels table.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=settings.app_log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    init_db()
    _seed_defaults()
    start_scheduler()
    start_poller()
    logger.info("Agentic app started.")
    try:
        yield
    finally:
        stop_poller()
        stop_scheduler()
        logger.info("Agentic app stopped.")


app = FastAPI(title="Personal Assistant — Morning Brief", lifespan=lifespan)
app.include_router(whatsapp_router)
app.include_router(reauth_router)


@app.get("/favicon.svg", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(Path(__file__).parent / "favicon.svg", media_type="image/svg+xml")


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/settings")


@app.get("/healthz")
def healthz() -> dict[str, str | datetime]:
    return {"status": "ok", "now": datetime.utcnow()}


@app.post("/run-now")
def run_now(background_tasks: BackgroundTasks) -> dict[str, str]:
    """Kick off a morning brief immediately. Returns immediately; work runs in background."""
    background_tasks.add_task(run_morning_brief, "manual")
    return {"status": "scheduled", "message": "Brief is being generated in the background."}


@app.get("/history")
def history(limit: int = 20) -> JSONResponse:
    with session_scope() as s:
        rows = s.execute(select(Run).order_by(desc(Run.started_at)).limit(limit)).scalars().all()
        out = [
            {
                "id": r.id,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "status": r.status,
                "trigger": r.trigger,
                "error": r.error,
            }
            for r in rows
        ]
    return JSONResponse(out)


@app.get("/history/{run_id}", response_class=HTMLResponse)
def history_one(run_id: int) -> HTMLResponse:
    with session_scope() as s:
        run = s.get(Run, run_id)
        if not run:
            raise HTTPException(404, "run not found")
        brief = s.execute(
            select(Brief).where(Brief.run_id == run_id).order_by(desc(Brief.created_at)).limit(1)
        ).scalar_one_or_none()
    body = brief.body_markdown if brief else "(no brief was produced for this run)"
    return HTMLResponse(
        f"""<!doctype html>
<html><head><title>Brief #{run_id}</title>
<style>body{{font-family:ui-sans-serif,system-ui;max-width:760px;margin:2rem auto;padding:0 1rem;}}
pre{{white-space:pre-wrap;background:#f6f8fa;padding:1rem;border-radius:8px;}}</style>
</head><body>
<h1>Brief #{run_id}</h1>
<p><b>Status:</b> {run.status} &nbsp; <b>Trigger:</b> {run.trigger}</p>
<p><b>Started:</b> {run.started_at} &nbsp; <b>Finished:</b> {run.finished_at}</p>
<pre>{body}</pre>
</body></html>"""
    )


# ---------------------------------------------------------------------------
# Reminders — CRUD API
# ---------------------------------------------------------------------------

class ReminderIn(BaseModel):
    label: str
    frequency: str          # "daily" | "weekly" | "monthly"
    day_of_week: str | None = None
    day_of_month: int | None = None
    time: str | None = None
    time_end: str | None = None
    enabled: bool = True


class ReminderPatch(BaseModel):
    enabled: bool


def _reminder_dict(r: Reminder) -> dict:
    return {
        "id": r.id,
        "label": r.label,
        "frequency": r.frequency,
        "day_of_week": r.day_of_week,
        "day_of_month": r.day_of_month,
        "time": r.time,
        "time_end": r.time_end,
        "enabled": r.enabled,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@app.get("/reminders")
def list_reminders() -> JSONResponse:
    with session_scope() as s:
        rows = s.execute(select(Reminder).order_by(Reminder.created_at)).scalars().all()
        out = [_reminder_dict(r) for r in rows]
    return JSONResponse(out)


@app.post("/reminders", status_code=201)
def create_reminder(body: ReminderIn) -> JSONResponse:
    if body.frequency not in ("daily", "weekly", "monthly"):
        raise HTTPException(422, "frequency must be daily, weekly, or monthly")
    with session_scope() as s:
        r = Reminder(
            label=body.label,
            frequency=body.frequency,
            day_of_week=body.day_of_week,
            day_of_month=body.day_of_month,
            time=body.time,
            time_end=body.time_end,
            enabled=body.enabled,
        )
        s.add(r)
        s.flush()
        out = _reminder_dict(r)
    return JSONResponse(out, status_code=201)


@app.patch("/reminders/{reminder_id}")
def patch_reminder(reminder_id: int, body: ReminderPatch) -> JSONResponse:
    with session_scope() as s:
        r = s.get(Reminder, reminder_id)
        if not r:
            raise HTTPException(404, "reminder not found")
        r.enabled = body.enabled
        out = _reminder_dict(r)
    return JSONResponse(out)


@app.delete("/reminders/{reminder_id}", status_code=204)
def delete_reminder(reminder_id: int) -> None:
    with session_scope() as s:
        r = s.get(Reminder, reminder_id)
        if not r:
            raise HTTPException(404, "reminder not found")
        s.delete(r)


# ---------------------------------------------------------------------------
# Feature flags — gmail / youtube on/off
# ---------------------------------------------------------------------------

@app.get("/settings/flags")
def get_flags() -> JSONResponse:
    with session_scope() as s:
        rows = s.execute(select(AppSetting)).scalars().all()
        flags = {r.key: r.value for r in rows}
    return JSONResponse({
        "gmail_enabled": flags.get("gmail_enabled", "true") == "true",
        "youtube_enabled": flags.get("youtube_enabled", "true") == "true",
    })


class FlagPatch(BaseModel):
    value: bool


@app.patch("/settings/flags/{key}")
def set_flag(key: str, body: FlagPatch) -> JSONResponse:
    if key not in ("gmail_enabled", "youtube_enabled"):
        raise HTTPException(422, "unknown flag")
    with session_scope() as s:
        row = s.get(AppSetting, key)
        if row:
            row.value = "true" if body.value else "false"
        else:
            s.add(AppSetting(key=key, value="true" if body.value else "false"))
    return JSONResponse({"key": key, "value": body.value})


# ---------------------------------------------------------------------------
# YouTube channels CRUD
# ---------------------------------------------------------------------------

class ChannelIn(BaseModel):
    handle: str


@app.get("/channels")
def list_channels() -> JSONResponse:
    with session_scope() as s:
        rows = s.execute(select(YoutubeChannel).order_by(YoutubeChannel.added_at)).scalars().all()
        out = [{"id": r.id, "handle": r.handle, "added_at": r.added_at.isoformat()} for r in rows]
    return JSONResponse(out)


@app.post("/channels", status_code=201)
def add_channel(body: ChannelIn) -> JSONResponse:
    handle = body.handle.strip()
    if not handle:
        raise HTTPException(422, "handle must not be empty")
    with session_scope() as s:
        existing = s.execute(select(YoutubeChannel).where(YoutubeChannel.handle == handle)).scalar_one_or_none()
        if existing:
            raise HTTPException(409, "channel already exists")
        ch = YoutubeChannel(handle=handle)
        s.add(ch)
        s.flush()
        out = {"id": ch.id, "handle": ch.handle, "added_at": ch.added_at.isoformat()}
    return JSONResponse(out, status_code=201)


@app.delete("/channels/{channel_id}", status_code=204)
def delete_channel(channel_id: int) -> None:
    with session_scope() as s:
        ch = s.get(YoutubeChannel, channel_id)
        if not ch:
            raise HTTPException(404, "channel not found")
        s.delete(ch)


# ---------------------------------------------------------------------------
# Settings portal — mobile-friendly web UI
# ---------------------------------------------------------------------------

_SETTINGS_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Personal Assistant — Settings</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg:      #0d0d0d;
      --surface: #1a1a1a;
      --border:  #2a2a2a;
      --text:    #e5e5e5;
      --muted:   #888;
      --label:   #aaa;
      --accent:  #0a84ff;
      --green:   #30d158;
      --red:     #ff453a;
      --input-bg:#111;
    }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: var(--bg); color: var(--text); }
    .container { max-width: 600px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }
    h1 { font-size: 1.4rem; font-weight: 700; margin-bottom: 1.5rem; color: #fff; }
    h2 { font-size: 0.78rem; font-weight: 600; margin: 1.5rem 0 0.5rem;
         color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }
    .card { background: var(--surface); border: 1px solid var(--border);
            border-radius: 12px; padding: 0.25rem 1rem; margin-bottom: 1rem; }
    .row { display: flex; align-items: center; gap: 0.75rem;
           padding: 0.75rem 0; border-bottom: 1px solid var(--border); }
    .row:last-child { border-bottom: none; }
    .row-label { flex: 1; }
    .row-label strong { display: block; font-size: 0.95rem; color: var(--text); }
    .row-label small { color: var(--muted); font-size: 0.78rem; }
    /* toggle switch */
    .toggle { position: relative; width: 44px; height: 26px; flex-shrink: 0; }
    .toggle input { opacity: 0; width: 0; height: 0; position: absolute; }
    .slider { position: absolute; cursor: pointer; inset: 0;
              background: #3a3a3a; border-radius: 26px; transition: .2s; }
    .slider::before { content: ""; position: absolute; width: 20px; height: 20px;
                      left: 3px; top: 3px; background: #fff; border-radius: 50%; transition: .2s; }
    input:checked + .slider { background: var(--green); }
    input:checked + .slider::before { transform: translateX(18px); }
    .btn-del { background: none; border: none; font-size: 1.1rem;
               cursor: pointer; color: var(--red); padding: 0.2rem 0.1rem; }
    /* form */
    .form-card { background: var(--surface); border: 1px solid var(--border);
                 border-radius: 12px; padding: 1rem; margin-bottom: 1rem; }
    .form-card label { display: block; font-size: 0.82rem; font-weight: 600;
                       color: var(--label); margin-bottom: 0.25rem; }
    .form-card input[type=text],
    .form-card input[type=time],
    .form-card input[type=number],
    .form-card select {
      width: 100%; padding: 0.55rem 0.75rem;
      border: 1px solid var(--border); border-radius: 8px;
      font-size: 0.95rem; margin-bottom: 0.9rem;
      background: var(--input-bg); color: var(--text);
      appearance: auto; color-scheme: dark;
    }
    .inline-form { display: flex; gap: 0.5rem; margin-top: 0.5rem; }
    .inline-form input { flex: 1; padding: 0.55rem 0.75rem;
                         border: 1px solid var(--border); border-radius: 8px;
                         font-size: 0.95rem; background: var(--input-bg); color: var(--text); }
    .inline-form button { padding: 0.55rem 1rem; background: var(--accent); color: #fff;
                          border: none; border-radius: 8px; font-size: 0.9rem;
                          font-weight: 600; cursor: pointer; white-space: nowrap; }
    .freq-row { display: flex; gap: 0.5rem; margin-bottom: 0.9rem; }
    .freq-btn { flex: 1; padding: 0.5rem 0.25rem; border: 1.5px solid var(--border);
                border-radius: 8px; background: var(--input-bg); color: var(--muted);
                cursor: pointer; font-size: 0.82rem; font-weight: 500; transition: .15s; }
    .freq-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
    .conditional { display: none; }
    .conditional.show { display: block; }
    .btn-add { width: 100%; padding: 0.75rem; background: var(--accent); color: #fff;
               border: none; border-radius: 10px; font-size: 1rem;
               font-weight: 600; cursor: pointer; margin-top: 0.25rem; }
    .btn-add:active { opacity: 0.8; }
    .empty { color: var(--muted); font-size: 0.88rem; text-align: center;
             padding: 1.25rem 0; }
    .toast { position: fixed; bottom: 1.5rem; left: 50%; transform: translateX(-50%);
             background: #2a2a2a; color: #fff; padding: 0.6rem 1.2rem;
             border-radius: 20px; font-size: 0.88rem; opacity: 0;
             transition: opacity .3s; pointer-events: none;
             border: 1px solid var(--border); }
    .toast.show { opacity: 1; }
  </style>
</head>
<body>
<div class="container">
  <h1>⚙️ Personal Assistant — Settings</h1>

  <!-- ── Brief sections on/off ── -->
  <h2>📬 Brief Sections</h2>
  <div class="card">
    <div class="row">
      <div class="row-label">
        <strong>📧 Email Brief</strong>
        <small>Include Gmail summary in the morning brief</small>
      </div>
      <label class="toggle">
        <input type="checkbox" id="flag-gmail" onchange="setFlag('gmail_enabled', this.checked)">
        <span class="slider"></span>
      </label>
    </div>
    <div class="row">
      <div class="row-label">
        <strong>📺 YouTube Brief</strong>
        <small>Include YouTube video TL;DRs in the morning brief</small>
      </div>
      <label class="toggle">
        <input type="checkbox" id="flag-youtube" onchange="setFlag('youtube_enabled', this.checked)">
        <span class="slider"></span>
      </label>
    </div>
  </div>

  <!-- ── YouTube Channels ── -->
  <h2>📺 YouTube Channels</h2>
  <div class="card" id="channels-list"></div>
  <div class="form-card" style="margin-bottom:1rem;">
    <label>Add Channel</label>
    <div class="inline-form">
      <input id="ch-handle" type="text" placeholder="@channelhandle or UCxxxx…">
      <button onclick="addChannel()">Add</button>
    </div>
  </div>

  <!-- ── Recurring Reminders ── -->
  <h2>🔁 Recurring Reminders</h2>
  <div class="card" id="list"></div>

  <h2>Add Reminder</h2>
  <div class="form-card">
    <label>Label</label>
    <input id="f-label" type="text" placeholder="e.g. Review finances">

    <label>Frequency</label>
    <div class="freq-row">
      <button class="freq-btn active" data-f="daily"   onclick="setFreq('daily')">Daily</button>
      <button class="freq-btn"        data-f="weekly"  onclick="setFreq('weekly')">Weekly</button>
      <button class="freq-btn"        data-f="monthly" onclick="setFreq('monthly')">Monthly</button>
    </div>

    <div id="opt-weekly" class="conditional">
      <label>Day of week</label>
      <select id="f-dow">
        <option value="monday">Monday</option><option value="tuesday">Tuesday</option>
        <option value="wednesday">Wednesday</option><option value="thursday">Thursday</option>
        <option value="friday">Friday</option><option value="saturday">Saturday</option>
        <option value="sunday">Sunday</option>
      </select>
    </div>

    <div id="opt-monthly" class="conditional">
      <label>Day of month</label>
      <input id="f-dom" type="number" min="1" max="31" placeholder="1 – 31">
    </div>

    <label>Start Time (optional)</label>
    <input id="f-time" type="time">

    <label>End Time (optional)</label>
    <input id="f-time-end" type="time">

    <button class="btn-add" onclick="addReminder()">Add Reminder</button>
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
  // ── Flags ──────────────────────────────────────────────────────────────────
  async function loadFlags() {
    const res = await fetch('/settings/flags');
    const data = await res.json();
    document.getElementById('flag-gmail').checked = data.gmail_enabled;
    document.getElementById('flag-youtube').checked = data.youtube_enabled;
  }

  async function setFlag(key, value) {
    await fetch('/settings/flags/' + key, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({value}),
    });
    showToast(value ? 'Enabled ✓' : 'Disabled');
  }

  // ── YouTube Channels ───────────────────────────────────────────────────────
  async function loadChannels() {
    const res = await fetch('/channels');
    const data = await res.json();
    const el = document.getElementById('channels-list');
    if (!data.length) {
      el.innerHTML = '<p class="empty">No channels yet — add one below.</p>';
      return;
    }
    el.innerHTML = data.map(c => `
      <div class="row" id="ch-${c.id}">
        <div class="row-label">
          <strong>${esc(c.handle)}</strong>
        </div>
        <button class="btn-del" onclick="delChannel(${c.id})" title="Remove">🗑</button>
      </div>`).join('');
  }

  async function addChannel() {
    const handle = document.getElementById('ch-handle').value.trim();
    if (!handle) { showToast('Enter a channel handle.'); return; }
    const res = await fetch('/channels', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({handle}),
    });
    if (res.status === 409) { showToast('Channel already added.'); return; }
    document.getElementById('ch-handle').value = '';
    showToast('Channel added ✓');
    loadChannels();
  }

  async function delChannel(id) {
    if (!confirm('Remove this channel?')) return;
    await fetch('/channels/' + id, {method: 'DELETE'});
    showToast('Removed');
    loadChannels();
  }

  // ── Reminders ─────────────────────────────────────────────────────────────
  let freq = 'daily';

  function setFreq(f) {
    freq = f;
    document.querySelectorAll('.freq-btn').forEach(b =>
      b.classList.toggle('active', b.dataset.f === f));
    document.getElementById('opt-weekly').classList.toggle('show', f === 'weekly');
    document.getElementById('opt-monthly').classList.toggle('show', f === 'monthly');
  }

  function esc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function ordinal(n) {
    if (n >= 11 && n <= 13) return 'th';
    return ({1:'st',2:'nd',3:'rd'})[n % 10] || 'th';
  }

  function freqLabel(r) {
    if (r.frequency === 'daily') return 'Every day';
    if (r.frequency === 'weekly')
      return 'Every ' + r.day_of_week.charAt(0).toUpperCase() + r.day_of_week.slice(1);
    if (r.frequency === 'monthly')
      return 'Monthly on the ' + r.day_of_month + ordinal(r.day_of_month);
    return r.frequency;
  }

  async function load() {
    const res = await fetch('/reminders');
    const data = await res.json();
    const el = document.getElementById('list');
    if (!data.length) {
      el.innerHTML = '<p class="empty">No reminders yet — add one below.</p>';
      return;
    }
    el.innerHTML = data.map(r => `
      <div class="row" id="rem-${r.id}">
        <div class="row-label">
          <strong>${esc(r.label)}</strong>
          <small>${freqLabel(r)}${r.time ? ' at ' + r.time + (r.time_end ? '–' + r.time_end : '') : ''}</small>
        </div>
        <label class="toggle" title="${r.enabled ? 'Enabled' : 'Disabled'}">
          <input type="checkbox" ${r.enabled ? 'checked' : ''}
                 onchange="toggleReminder(${r.id}, this.checked)">
          <span class="slider"></span>
        </label>
        <button class="btn-del" onclick="del(${r.id})" title="Delete">🗑</button>
      </div>`).join('');
  }

  async function addReminder() {
    const label = document.getElementById('f-label').value.trim();
    if (!label) { showToast('Please enter a label.'); return; }
    const dom = parseInt(document.getElementById('f-dom').value);
    if (freq === 'monthly' && (!dom || dom < 1 || dom > 31)) {
      showToast('Enter a valid day of month (1–31).'); return;
    }
    await fetch('/reminders', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        label,
        frequency: freq,
        day_of_week: freq === 'weekly' ? document.getElementById('f-dow').value : null,
        day_of_month: freq === 'monthly' ? dom : null,
        time: document.getElementById('f-time').value || null,
        time_end: document.getElementById('f-time-end').value || null,
        enabled: true,
      }),
    });
    document.getElementById('f-label').value = '';
    document.getElementById('f-time').value = '';
    document.getElementById('f-time-end').value = '';
    showToast('Reminder added ✓');
    load();
  }

  async function toggleReminder(id, enabled) {
    await fetch('/reminders/' + id, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({enabled}),
    });
    showToast(enabled ? 'Enabled ✓' : 'Disabled');
  }

  async function del(id) {
    if (!confirm('Delete this reminder?')) return;
    await fetch('/reminders/' + id, {method: 'DELETE'});
    showToast('Deleted');
    load();
  }

  // ── Toast ──────────────────────────────────────────────────────────────────
  let _toastTimer;
  function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => t.classList.remove('show'), 2200);
  }

  // ── Init ───────────────────────────────────────────────────────────────────
  loadFlags();
  loadChannels();
  load();
</script>
</body>
</html>"""


@app.get("/settings", response_class=HTMLResponse)
def settings_portal() -> HTMLResponse:
    return HTMLResponse(_SETTINGS_HTML)
