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

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import desc, select

from .config import get_settings
from .db import init_db, session_scope
from .models import Brief, Reminder, Run
from .routers.whatsapp import router as whatsapp_router
from .scheduler import start_scheduler, stop_scheduler
from .telegram_poller import start_poller, stop_poller
from .workflow import run_morning_brief

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=settings.app_log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    init_db()
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
# Settings portal — mobile-friendly web UI
# ---------------------------------------------------------------------------

_SETTINGS_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Personal Assistant — Settings</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #f5f5f7; color: #1d1d1f; }
    .container { max-width: 600px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }
    h1 { font-size: 1.4rem; font-weight: 700; margin-bottom: 1.5rem; }
    h2 { font-size: 1rem; font-weight: 600; margin: 1.5rem 0 0.75rem; color: #555; }
    .card { background: #fff; border-radius: 12px; padding: 0.25rem 1rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 1rem; }
    .row { display: flex; align-items: center; gap: 0.75rem;
           padding: 0.75rem 0; border-bottom: 1px solid #f0f0f0; }
    .row:last-child { border-bottom: none; }
    .row-label { flex: 1; }
    .row-label strong { display: block; font-size: 0.95rem; }
    .row-label small { color: #888; font-size: 0.78rem; }
    /* toggle switch */
    .toggle { position: relative; width: 44px; height: 26px; flex-shrink: 0; }
    .toggle input { opacity: 0; width: 0; height: 0; position: absolute; }
    .slider { position: absolute; cursor: pointer; inset: 0;
              background: #ccc; border-radius: 26px; transition: .2s; }
    .slider::before { content: ""; position: absolute; width: 20px; height: 20px;
                      left: 3px; top: 3px; background: #fff; border-radius: 50%; transition: .2s; }
    input:checked + .slider { background: #34c759; }
    input:checked + .slider::before { transform: translateX(18px); }
    .btn-del { background: none; border: none; font-size: 1.1rem;
               cursor: pointer; color: #ff3b30; padding: 0.2rem 0.1rem; }
    /* form */
    .form-card { background: #fff; border-radius: 12px; padding: 1rem;
                 box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
    .form-card label { display: block; font-size: 0.82rem; font-weight: 600;
                       color: #555; margin-bottom: 0.25rem; }
    .form-card input[type=text],
    .form-card input[type=time],
    .form-card input[type=number],
    .form-card select {
      width: 100%; padding: 0.55rem 0.75rem; border: 1px solid #ddd;
      border-radius: 8px; font-size: 0.95rem; margin-bottom: 0.9rem;
      appearance: auto;
    }
    .freq-row { display: flex; gap: 0.5rem; margin-bottom: 0.9rem; }
    .freq-btn { flex: 1; padding: 0.5rem 0.25rem; border: 1.5px solid #ddd;
                border-radius: 8px; background: #fff; cursor: pointer;
                font-size: 0.82rem; font-weight: 500; transition: .15s; }
    .freq-btn.active { background: #007aff; color: #fff; border-color: #007aff; }
    .conditional { display: none; }
    .conditional.show { display: block; }
    .btn-add { width: 100%; padding: 0.75rem; background: #007aff; color: #fff;
               border: none; border-radius: 10px; font-size: 1rem;
               font-weight: 600; cursor: pointer; margin-top: 0.25rem; }
    .btn-add:active { opacity: 0.8; }
    .empty { color: #aaa; font-size: 0.88rem; text-align: center;
             padding: 1.25rem 0; }
    .toast { position: fixed; bottom: 1.5rem; left: 50%; transform: translateX(-50%);
             background: #323232; color: #fff; padding: 0.6rem 1.2rem;
             border-radius: 20px; font-size: 0.88rem; opacity: 0;
             transition: opacity .3s; pointer-events: none; }
    .toast.show { opacity: 1; }
  </style>
</head>
<body>
<div class="container">
  <h1>⚙️ Personal Assistant — Settings</h1>

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

    <label>Time (optional)</label>
    <input id="f-time" type="time">

    <button class="btn-add" onclick="addReminder()">Add Reminder</button>
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
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
          <small>${freqLabel(r)}${r.time ? ' at ' + r.time : ''}</small>
        </div>
        <label class="toggle" title="${r.enabled ? 'Enabled' : 'Disabled'}">
          <input type="checkbox" ${r.enabled ? 'checked' : ''}
                 onchange="toggle(${r.id}, this.checked)">
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
        enabled: true,
      }),
    });
    document.getElementById('f-label').value = '';
    document.getElementById('f-time').value = '';
    showToast('Reminder added ✓');
    load();
  }

  async function toggle(id, enabled) {
    await fetch(`/reminders/${id}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({enabled}),
    });
    showToast(enabled ? 'Enabled ✓' : 'Disabled');
  }

  async function del(id) {
    if (!confirm('Delete this reminder?')) return;
    await fetch(`/reminders/${id}`, {method: 'DELETE'});
    showToast('Deleted');
    load();
  }

  let _toastTimer;
  function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => t.classList.remove('show'), 2200);
  }

  load();
</script>
</body>
</html>"""


@app.get("/settings", response_class=HTMLResponse)
def settings_portal() -> HTMLResponse:
    return HTMLResponse(_SETTINGS_HTML)
