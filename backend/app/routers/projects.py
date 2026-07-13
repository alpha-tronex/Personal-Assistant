"""Projects status dashboard.

Endpoints:
  GET /projects -> dashboard showing done/todo status for side projects

Done/todo bullets are curated by hand in config/projects.yaml (repo docs
are too inconsistent across projects to auto-parse reliably). Each project
also gets a live "last commit" line per repo, pulled from the public GitHub
API (unauthenticated — fine for the request volume of a single page load).
"""

from __future__ import annotations

import html
import logging
from datetime import datetime, timezone

import httpx
import yaml
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import BACKEND_ROOT

logger = logging.getLogger(__name__)
router = APIRouter()

PROJECTS_FILE = BACKEND_ROOT / "config" / "projects.yaml"


@retry(
    reraise=True,
    stop=stop_after_attempt(2),
    wait=wait_exponential(min=1, max=4),
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
)
def _fetch_latest_commit(repo: str) -> dict | None:
    """Return {'message', 'date', 'sha'} for repo's (owner/name) default-branch HEAD."""
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
    return {
        "message": commit["message"].splitlines()[0],
        "date": commit["author"]["date"],
        "sha": data[0]["sha"][:7],
    }


def _load_projects() -> list[dict]:
    if not PROJECTS_FILE.exists():
        return []
    data = yaml.safe_load(PROJECTS_FILE.read_text()) or {}
    return data.get("projects") or []


def _fmt_relative(iso_date: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except ValueError:
        return iso_date
    days = (datetime.now(timezone.utc) - dt).days
    if days <= 0:
        return "today"
    if days == 1:
        return "1 day ago"
    if days < 30:
        return f"{days} days ago"
    months = days // 30
    return f"{months} month{'s' if months != 1 else ''} ago"


def _render_project(project: dict) -> str:
    name = html.escape(project.get("name", "Untitled"))
    tagline = html.escape(project.get("tagline", ""))
    done = project.get("done") or []
    todo = project.get("todo") or []
    repos = project.get("repos") or []

    commit_rows = []
    for repo in repos:
        info = None
        try:
            info = _fetch_latest_commit(repo)
        except Exception as e:  # noqa: BLE001 - one repo's failure shouldn't break the page
            logger.warning("GitHub fetch failed for %s: %s", repo, e)
        repo_label = html.escape(repo)
        if info:
            msg = html.escape(info["message"])
            when = _fmt_relative(info["date"])
            commit_rows.append(
                f'<div class="commit-row"><span class="repo-name">{repo_label}</span> '
                f'<span class="commit-msg">&ldquo;{msg}&rdquo;</span> '
                f'<span class="commit-when">{when}</span></div>'
            )
        else:
            commit_rows.append(
                f'<div class="commit-row"><span class="repo-name">{repo_label}</span> '
                f'<span class="commit-when muted">unavailable</span></div>'
            )

    done_html = "".join(f"<li>{html.escape(item)}</li>" for item in done) or "<li class='empty'>Nothing recorded</li>"
    todo_html = "".join(f"<li>{html.escape(item)}</li>" for item in todo) or "<li class='empty'>Nothing recorded</li>"

    return f"""
    <div class="card">
      <h2>{name}</h2>
      <p class="tagline">{tagline}</p>
      <div class="commits">{''.join(commit_rows)}</div>
      <div class="cols">
        <div>
          <div class="col-label">Done</div>
          <ul>{done_html}</ul>
        </div>
        <div>
          <div class="col-label">To do</div>
          <ul>{todo_html}</ul>
        </div>
      </div>
    </div>
    """


_PAGE_TEMPLATE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Projects - Status Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <style>
    :root {{
      --bg:#0d0d0d; --surface:#1a1a1a; --border:#2a2a2a; --text:#e5e5e5;
      --muted:#888; --label:#aaa; --accent:#0a84ff; --green:#30d158; --red:#ff453a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      background: var(--bg); color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
    }}
    .container {{ max-width: 720px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }}
    h1 {{ font-size: 1.4rem; margin-bottom: 0.25rem; }}
    .subtitle {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 1.5rem; }}
    .card {{
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 12px; padding: 1rem 1.25rem; margin-bottom: 1rem;
    }}
    .card h2 {{ margin: 0 0 0.15rem; font-size: 1.1rem; }}
    .tagline {{ color: var(--muted); font-size: 0.85rem; margin: 0 0 0.75rem; }}
    .commits {{ margin-bottom: 0.75rem; }}
    .commit-row {{ font-size: 0.8rem; color: var(--label); margin-bottom: 0.2rem; overflow: hidden; }}
    .repo-name {{ color: var(--accent); font-family: ui-monospace, monospace; margin-right: 0.4rem; }}
    .commit-msg {{ color: var(--text); }}
    .commit-when {{ color: var(--muted); float: right; }}
    .commit-when.muted {{ font-style: italic; }}
    .cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
    @media (max-width: 480px) {{ .cols {{ grid-template-columns: 1fr; }} }}
    .col-label {{ font-size: 0.8rem; color: var(--label); font-weight: 600; margin-bottom: 0.35rem; }}
    ul {{ margin: 0; padding-left: 1.1rem; font-size: 0.85rem; }}
    li {{ margin-bottom: 0.3rem; }}
    li.empty {{ color: var(--muted); list-style: none; margin-left: -1.1rem; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Projects</h1>
    <div class="subtitle">Status across active side projects. Done/to-do curated by hand, commit info live from GitHub.</div>
    {cards}
  </div>
</body>
</html>"""


@router.get("/projects", response_class=HTMLResponse)
def projects_dashboard() -> HTMLResponse:
    projects = _load_projects()
    cards = "".join(_render_project(p) for p in projects) or "<p>No projects configured.</p>"
    return HTMLResponse(_PAGE_TEMPLATE.format(cards=cards))
