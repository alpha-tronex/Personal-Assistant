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
from sqlalchemy import desc, select

from .config import get_settings
from .db import init_db, session_scope
from .models import Brief, Run
from .scheduler import start_scheduler, stop_scheduler
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
    logger.info("Agentic app started.")
    try:
        yield
    finally:
        stop_scheduler()
        logger.info("Agentic app stopped.")


app = FastAPI(title="Personal Assistant — Morning Brief", lifespan=lifespan)


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
