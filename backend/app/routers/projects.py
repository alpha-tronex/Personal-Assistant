"""Projects status dashboard.

Endpoints:
  GET   /projects              -> dashboard
  PATCH /projects/{name}       -> update done/todo lists (saves to projects.yaml)
  GET   /projects/{name}/commits -> re-fetch latest commit data from GitHub
"""

from __future__ import annotations

import html
import json
import logging
import math
from datetime import datetime, timezone

import httpx
import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import BACKEND_ROOT

logger = logging.getLogger(__name__)
router = APIRouter()

PROJECTS_FILE = BACKEND_ROOT / "config" / "projects.yaml"

# Circumference of the gauge ring (r=28)
_CIRC = 2 * math.pi * 28


# ── GitHub helpers ────────────────────────────────────────────────────────────

@retry(
    reraise=True,
    stop=stop_after_attempt(2),
    wait=wait_exponential(min=1, max=4),
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
)
def _fetch_latest_commit(repo: str) -> dict | None:
    """Return {'message', 'date', 'sha', 'days'} for repo's default-branch HEAD."""
    url = f"https://api.github.com/repos/{repo}/commits"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "personal-assistant-dashboard",
    }
    with httpx.Client(timeout=8.0) as client:
        r = client.get(url, headers=headers, params={"per_page": 1})
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    commit = data[0]["commit"]
    iso = commit["author"]["date"]
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - dt).days
    except ValueError:
        days = 9999
    return {
        "message": commit["message"].splitlines()[0],
        "date": iso,
        "sha": data[0]["sha"][:7],
        "days": days,
        "repo": repo,
    }


# ── YAML helpers ──────────────────────────────────────────────────────────────

def _load_projects() -> list[dict]:
    if not PROJECTS_FILE.exists():
        return []
    data = yaml.safe_load(PROJECTS_FILE.read_text()) or {}
    return data.get("projects") or []


def _save_projects(projects: list[dict]) -> None:
    PROJECTS_FILE.write_text(
        yaml.dump({"projects": projects}, allow_unicode=True, sort_keys=False, default_flow_style=False)
    )


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_relative(days: int) -> str:
    if days <= 0:
        return "today"
    if days == 1:
        return "1 day ago"
    if days < 30:
        return f"{days} days ago"
    months = days // 30
    return f"{months} month{'s' if months != 1 else ''} ago"


def _freshness(days: int) -> tuple[str, str]:
    if days <= 7:
        return "fresh-active", "Active"
    if days <= 30:
        return "fresh-recent", "Recent"
    if days <= 90:
        return "fresh-slow", "Slow"
    return "fresh-dormant", "Dormant"


def _gauge_svg(pct: int) -> str:
    filled = _CIRC * pct / 100
    r = 28
    cx = cy = 34
    return (
        f'<svg class="gauge-svg" viewBox="0 0 68 68" xmlns="http://www.w3.org/2000/svg">'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="var(--border)" stroke-width="6"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="var(--gauge-color)" stroke-width="6"'
        f' stroke-linecap="round"'
        f' stroke-dasharray="{filled:.1f} {_CIRC:.1f}"'
        f' transform="rotate(-90 {cx} {cy})"/>'
        f'<text x="{cx}" y="{cy}" dominant-baseline="central" text-anchor="middle"'
        f' fill="var(--text)" font-size="13" font-weight="700" font-family="-apple-system,sans-serif">'
        f'{pct}%</text>'
        f'</svg>'
    )


def _commit_rows_html(repos: list[str]) -> tuple[str, int]:
    """Fetch commits for all repos, return (html, min_days)."""
    min_days = 9999
    rows = []
    for repo in repos:
        info = None
        try:
            info = _fetch_latest_commit(repo)
        except Exception as e:  # noqa: BLE001
            logger.warning("GitHub fetch failed for %s: %s", repo, e)
        repo_label = html.escape(repo.split("/")[-1])
        if info:
            min_days = min(min_days, info["days"])
            rows.append(
                f'<div class="commit-row">'
                f'<span class="repo-name">{repo_label}</span>'
                f'<span class="commit-sha">{html.escape(info["sha"])}</span>'
                f'<span class="commit-msg">{html.escape(info["message"])}</span>'
                f'<span class="commit-when">{_fmt_relative(info["days"])}</span>'
                f'</div>'
            )
        else:
            rows.append(
                f'<div class="commit-row">'
                f'<span class="repo-name">{repo_label}</span>'
                f'<span class="commit-when muted">unavailable</span>'
                f'</div>'
            )
    return "".join(rows), min_days


# ── Card renderer ─────────────────────────────────────────────────────────────

def _card_slug(name: str) -> str:
    return name.lower().replace(" ", "-").replace("/", "-")


def _render_project(project: dict) -> tuple[str, int]:
    """Return (card_html, min_days_since_commit) for sorting."""
    raw_name = project.get("name", "Untitled")
    name     = html.escape(raw_name)
    tagline  = html.escape(project.get("tagline", ""))
    done     = project.get("done") or []
    todo     = project.get("todo") or []
    repos    = project.get("repos") or []
    slug     = _card_slug(raw_name)

    total = len(done) + len(todo)
    pct   = round(len(done) * 100 / total) if total else 0

    gauge_color = "#30d158" if pct >= 75 else ("#ffd60a" if pct >= 40 else "#0a84ff")

    commit_html, min_days = _commit_rows_html(repos)
    fresh_cls, fresh_label = _freshness(min_days) if min_days < 9999 else ("fresh-dormant", "No data")

    done_html = "".join(f"<li>{html.escape(item)}</li>" for item in done) or "<li class='muted-item'>—</li>"
    todo_html = "".join(f"<li>{html.escape(item)}</li>" for item in todo) or "<li class='muted-item'>—</li>"

    done_json = html.escape(json.dumps(done), quote=True)
    todo_json = html.escape(json.dumps(todo), quote=True)
    name_attr = html.escape(raw_name, quote=True)

    card_html = f"""
<div class="card" style="--gauge-color:{gauge_color}" data-slug="{slug}">
  <div class="card-top">
    <div class="card-meta">
      <div class="card-title-row">
        <h2>{name}</h2>
        <span class="badge {fresh_cls}" id="badge-{slug}">{fresh_label}</span>
        <button class="icon-btn" title="Edit progress"
          onclick="openEdit(this)"
          data-name="{name_attr}"
          data-done="{done_json}"
          data-todo="{todo_json}">✏️</button>
        <button class="icon-btn refresh-btn" title="Refresh commits from GitHub"
          onclick="refreshCommits(this, '{name_attr}')"
          data-slug="{slug}">↻</button>
      </div>
      <p class="tagline">{tagline}</p>
      <div class="stats-row">
        <span class="stat done-stat">✓ {len(done)} done</span>
        <span class="stat todo-stat">◎ {len(todo)} to do</span>
      </div>
    </div>
    <div class="gauge-wrap">{_gauge_svg(pct)}</div>
  </div>

  <div class="progress-track">
    <div class="progress-fill" style="width:{pct}%"></div>
  </div>

  <div class="commits" id="commits-{slug}">{commit_html}</div>

  <div class="lists">
    <div class="list-col">
      <div class="col-label">✅ Done</div>
      <ul>{done_html}</ul>
    </div>
    <div class="list-col">
      <div class="col-label">⏳ To do</div>
      <ul>{todo_html}</ul>
    </div>
  </div>
</div>
"""
    return card_html, min_days


# ── API endpoints ─────────────────────────────────────────────────────────────

class ProjectUpdate(BaseModel):
    done: list[str]
    todo: list[str]


@router.patch("/projects/{name}", response_class=JSONResponse)
def update_project(name: str, body: ProjectUpdate) -> JSONResponse:
    projects = _load_projects()
    for p in projects:
        if p.get("name", "").lower() == name.lower():
            p["done"] = [item.strip() for item in body.done if item.strip()]
            p["todo"] = [item.strip() for item in body.todo if item.strip()]
            _save_projects(projects)
            return JSONResponse({"ok": True})
    raise HTTPException(404, f"Project '{name}' not found")


@router.get("/projects/{name}/commits", response_class=JSONResponse)
def project_commits(name: str) -> JSONResponse:
    """Re-fetch latest commit data from GitHub for a single project."""
    projects = _load_projects()
    for p in projects:
        if p.get("name", "").lower() == name.lower():
            repos = p.get("repos") or []
            results = []
            min_days = 9999
            for repo in repos:
                try:
                    info = _fetch_latest_commit(repo)
                    if info:
                        min_days = min(min_days, info["days"])
                        results.append({
                            "repo": repo,
                            "sha": info["sha"],
                            "message": info["message"],
                            "days": info["days"],
                            "when": _fmt_relative(info["days"]),
                        })
                    else:
                        results.append({"repo": repo, "error": True})
                except Exception as e:  # noqa: BLE001
                    logger.warning("GitHub fetch failed for %s: %s", repo, e)
                    results.append({"repo": repo, "error": True})
            fresh_cls, fresh_label = _freshness(min_days) if min_days < 9999 else ("fresh-dormant", "No data")
            return JSONResponse({
                "ok": True,
                "commits": results,
                "fresh_cls": fresh_cls,
                "fresh_label": fresh_label,
            })
    raise HTTPException(404, f"Project '{name}' not found")


# ── Page template ─────────────────────────────────────────────────────────────

_PAGE_TEMPLATE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Projects — Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <style>
    :root {{
      --bg:#0d0d0d; --surface:#161616; --border:#252525; --border2:#2e2e2e;
      --text:#e5e5e5; --muted:#666; --label:#999;
      --accent:#0a84ff; --green:#30d158; --yellow:#ffd60a; --red:#ff453a;
      --gauge-color:#0a84ff;
    }}
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg); color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      min-height: 100vh;
    }}

    /* ── Header ── */
    .topbar {{
      border-bottom: 1px solid var(--border); padding: 1rem 1.5rem;
      display: flex; align-items: center; gap: 1rem;
    }}
    .topbar h1 {{ font-size: 1.1rem; font-weight: 700; }}
    .topbar .back {{ color: var(--label); font-size: 0.82rem; text-decoration: none; }}
    .topbar .back:hover {{ color: var(--text); }}
    .topbar .ts {{ margin-left: auto; color: var(--muted); font-size: 0.78rem; }}

    /* ── Summary strip ── */
    .summary {{
      display: flex; gap: 1rem; flex-wrap: wrap;
      padding: 0.9rem 1.5rem; border-bottom: 1px solid var(--border);
    }}
    .summary-pill {{
      background: var(--surface); border: 1px solid var(--border2);
      border-radius: 8px; padding: 0.45rem 0.85rem;
      font-size: 0.82rem; color: var(--label);
    }}
    .summary-pill strong {{ color: var(--text); }}

    /* ── Grid ── */
    .grid {{
      display: grid; grid-template-columns: 1fr 1fr;
      gap: 1rem; padding: 1.25rem 1.5rem 3rem;
      max-width: 1100px; margin: 0 auto;
    }}
    @media (max-width: 680px) {{ .grid {{ grid-template-columns: 1fr; padding: 1rem; }} }}

    /* ── Card ── */
    .card {{
      background: var(--surface); border: 1px solid var(--border2);
      border-radius: 14px; padding: 1.1rem 1.2rem;
      display: flex; flex-direction: column; gap: 0.75rem;
    }}
    .card-top {{ display: flex; align-items: flex-start; gap: 0.75rem; }}
    .card-meta {{ flex: 1; min-width: 0; }}
    .card-title-row {{
      display: flex; align-items: center; gap: 0.4rem;
      margin-bottom: 0.2rem; flex-wrap: wrap;
    }}
    .card-title-row h2 {{
      font-size: 1rem; font-weight: 700;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      margin-right: 0.1rem;
    }}
    .tagline {{ color: var(--muted); font-size: 0.78rem; margin-bottom: 0.5rem; line-height: 1.4; }}

    /* stats */
    .stats-row {{ display: flex; gap: 0.6rem; }}
    .stat {{ font-size: 0.75rem; padding: 0.2rem 0.55rem; border-radius: 20px; font-weight: 500; }}
    .done-stat {{ background: rgba(48,209,88,.12); color: var(--green); }}
    .todo-stat {{ background: rgba(10,132,255,.1); color: var(--accent); }}

    /* freshness badge */
    .badge {{
      font-size: 0.68rem; font-weight: 600; padding: 0.18rem 0.5rem;
      border-radius: 20px; white-space: nowrap; flex-shrink: 0;
    }}
    .fresh-active  {{ background: rgba(48,209,88,.15);  color: var(--green); }}
    .fresh-recent  {{ background: rgba(255,214,10,.12); color: var(--yellow); }}
    .fresh-slow    {{ background: rgba(255,159,10,.12); color: #ff9f0a; }}
    .fresh-dormant {{ background: rgba(255,69,58,.12);  color: var(--red); }}

    /* icon buttons (pencil + refresh) */
    .icon-btn {{
      background: none; border: none; color: var(--muted);
      cursor: pointer; font-size: 0.85rem; padding: 0.1rem 0.2rem;
      border-radius: 4px; line-height: 1; flex-shrink: 0;
      transition: color .15s;
    }}
    .icon-btn:hover {{ color: var(--text); }}
    .refresh-btn {{ font-size: 1rem; }}
    .refresh-btn.spinning {{ animation: spin 0.8s linear infinite; }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}

    /* gauge */
    .gauge-wrap {{ flex-shrink: 0; }}
    .gauge-svg {{ width: 68px; height: 68px; }}

    /* progress bar */
    .progress-track {{ height: 4px; background: var(--border2); border-radius: 4px; overflow: hidden; }}
    .progress-fill {{ height: 100%; background: var(--gauge-color); border-radius: 4px; transition: width .4s ease; }}

    /* commit rows */
    .commits {{ display: flex; flex-direction: column; gap: 0.3rem; }}
    .commit-row {{
      display: grid; grid-template-columns: auto auto 1fr auto;
      align-items: center; gap: 0.4rem; font-size: 0.75rem; overflow: hidden;
    }}
    .repo-name {{ color: var(--accent); font-family: ui-monospace, monospace; font-size: 0.72rem; white-space: nowrap; }}
    .commit-sha {{ color: var(--muted); font-family: ui-monospace, monospace; font-size: 0.68rem; background: var(--border); padding: 0.1rem 0.3rem; border-radius: 4px; white-space: nowrap; }}
    .commit-msg {{ color: var(--label); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .commit-when {{ color: var(--muted); white-space: nowrap; font-size: 0.7rem; }}
    .commit-when.muted {{ font-style: italic; }}

    /* lists */
    .lists {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }}
    .col-label {{ font-size: 0.72rem; font-weight: 600; color: var(--label); margin-bottom: 0.3rem; letter-spacing: .02em; }}
    ul {{ padding-left: 1rem; }}
    li {{ font-size: 0.78rem; color: var(--label); margin-bottom: 0.25rem; line-height: 1.4; }}
    .muted-item {{ color: var(--muted); list-style: none; margin-left: -1rem; font-style: italic; }}

    /* modal */
    .modal-overlay {{
      display: none; position: fixed; inset: 0;
      background: rgba(0,0,0,.65); z-index: 100;
      align-items: center; justify-content: center; padding: 1rem;
    }}
    .modal-overlay.open {{ display: flex; }}
    .modal {{
      background: #1e1e1e; border: 1px solid var(--border2);
      border-radius: 16px; padding: 1.5rem; width: 100%; max-width: 520px;
      display: flex; flex-direction: column; gap: 1rem;
    }}
    .modal h3 {{ font-size: 1rem; }}
    .modal label {{ font-size: 0.78rem; color: var(--label); font-weight: 600; margin-bottom: 0.3rem; display: block; }}
    .modal textarea {{
      width: 100%; background: var(--bg); border: 1px solid var(--border2);
      color: var(--text); border-radius: 8px; padding: 0.6rem 0.75rem;
      font-size: 0.82rem; font-family: inherit; resize: vertical; min-height: 110px; line-height: 1.5;
    }}
    .modal-hint {{ font-size: 0.73rem; color: var(--muted); margin-top: -0.5rem; }}
    .modal-actions {{ display: flex; gap: 0.6rem; justify-content: flex-end; }}
    .btn-cancel {{
      background: none; border: 1px solid var(--border2); color: var(--label);
      border-radius: 8px; padding: 0.45rem 1rem; font-size: 0.85rem; cursor: pointer;
    }}
    .btn-save {{
      background: var(--accent); border: none; color: #fff;
      border-radius: 8px; padding: 0.45rem 1.2rem; font-size: 0.85rem;
      font-weight: 600; cursor: pointer;
    }}
    .btn-save:disabled {{ opacity: 0.5; cursor: default; }}
  </style>
</head>
<body>

<!-- Edit modal -->
<div class="modal-overlay" id="modal-overlay" onclick="closeOnBackdrop(event)">
  <div class="modal">
    <h3 id="modal-title">Edit project</h3>
    <div>
      <label>✅ Done <span class="modal-hint">— one item per line</span></label>
      <textarea id="modal-done" placeholder="What's been completed…"></textarea>
    </div>
    <div>
      <label>⏳ To do <span class="modal-hint">— one item per line</span></label>
      <textarea id="modal-todo" placeholder="What's still pending…"></textarea>
    </div>
    <div class="modal-actions">
      <button class="btn-cancel" onclick="closeModal()">Cancel</button>
      <button class="btn-save" id="modal-save" onclick="saveEdit()">Save</button>
    </div>
  </div>
</div>

<div class="topbar">
  <a class="back" href="/settings">← Settings</a>
  <h1>📊 Projects</h1>
  <span class="ts">Commit data live from GitHub</span>
</div>

<div class="summary">{summary}</div>

<div class="grid">{cards}</div>

<script>
  // ── Edit modal ──────────────────────────────────────────────────────────────
  let _currentProject = null;

  function openEdit(btn) {{
    _currentProject = btn.dataset.name;
    document.getElementById('modal-title').textContent = 'Edit — ' + _currentProject;
    document.getElementById('modal-done').value = JSON.parse(btn.dataset.done).join('\\n');
    document.getElementById('modal-todo').value = JSON.parse(btn.dataset.todo).join('\\n');
    document.getElementById('modal-save').disabled = false;
    document.getElementById('modal-save').textContent = 'Save';
    document.getElementById('modal-overlay').classList.add('open');
  }}

  function closeModal() {{
    document.getElementById('modal-overlay').classList.remove('open');
    _currentProject = null;
  }}

  function closeOnBackdrop(e) {{
    if (e.target === document.getElementById('modal-overlay')) closeModal();
  }}

  async function saveEdit() {{
    const btn = document.getElementById('modal-save');
    btn.disabled = true; btn.textContent = 'Saving…';
    const done = document.getElementById('modal-done').value.split('\\n').map(s => s.trim()).filter(Boolean);
    const todo = document.getElementById('modal-todo').value.split('\\n').map(s => s.trim()).filter(Boolean);
    const res = await fetch('/projects/' + encodeURIComponent(_currentProject), {{
      method: 'PATCH',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ done, todo }}),
    }});
    if (res.ok) {{ closeModal(); location.reload(); }}
    else {{ btn.textContent = 'Error — retry'; btn.disabled = false; }}
  }}

  // ── Commit refresh ──────────────────────────────────────────────────────────
  async function refreshCommits(btn, name) {{
    btn.classList.add('spinning');
    btn.disabled = true;
    try {{
      const res = await fetch('/projects/' + encodeURIComponent(name) + '/commits');
      if (!res.ok) throw new Error('fetch failed');
      const data = await res.json();

      // Update badge
      const slug = btn.dataset.slug;
      const badge = document.getElementById('badge-' + slug);
      badge.className = 'badge ' + data.fresh_cls;
      badge.textContent = data.fresh_label;

      // Rebuild commit rows
      const container = document.getElementById('commits-' + slug);
      container.innerHTML = data.commits.map(c => {{
        const repoName = c.repo.split('/').pop();
        if (c.error) {{
          return `<div class="commit-row">
            <span class="repo-name">${{repoName}}</span>
            <span class="commit-when muted">unavailable</span>
          </div>`;
        }}
        return `<div class="commit-row">
          <span class="repo-name">${{repoName}}</span>
          <span class="commit-sha">${{c.sha}}</span>
          <span class="commit-msg">${{c.message}}</span>
          <span class="commit-when">${{c.when}}</span>
        </div>`;
      }}).join('');
    }} catch(e) {{
      console.error('Refresh failed', e);
    }} finally {{
      btn.classList.remove('spinning');
      btn.disabled = false;
    }}
  }}
</script>

</body>
</html>"""


def _build_summary(projects: list[dict]) -> str:
    total_done = sum(len(p.get("done") or []) for p in projects)
    total_todo = sum(len(p.get("todo") or []) for p in projects)
    total_items = total_done + total_todo
    overall_pct = round(total_done * 100 / total_items) if total_items else 0
    return (
        f'<div class="summary-pill">🗂 <strong>{len(projects)}</strong> projects</div>'
        f'<div class="summary-pill">✅ <strong>{total_done}</strong> done</div>'
        f'<div class="summary-pill">⏳ <strong>{total_todo}</strong> to do</div>'
        f'<div class="summary-pill">📈 <strong>{overall_pct}%</strong> overall complete</div>'
    )


@router.get("/projects", response_class=HTMLResponse)
def projects_dashboard() -> HTMLResponse:
    projects = _load_projects()
    if not projects:
        cards = "<p style='color:var(--muted);padding:2rem'>No projects configured in config/projects.yaml.</p>"
        summary = ""
    else:
        rendered = [_render_project(p) for p in projects]
        rendered.sort(key=lambda x: x[1])
        cards   = "".join(c for c, _ in rendered)
        summary = _build_summary(projects)
    return HTMLResponse(_PAGE_TEMPLATE.format(cards=cards, summary=summary))
