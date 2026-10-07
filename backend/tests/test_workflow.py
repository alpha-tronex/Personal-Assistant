from __future__ import annotations

import pytest

from app import workflow
from app.db import session_scope
from app.models import Brief, Run


class FakeGraph:
    def __init__(self, result=None, exc: Exception | None = None):
        self.result, self.exc = result, exc

    def invoke(self, state):
        if self.exc:
            raise self.exc
        return self.result


@pytest.fixture
def alerts(monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(workflow, "send_telegram_message", sent.append)
    monkeypatch.setattr(workflow, "check_and_warn_token_age", lambda: None)
    return sent


def _rows():
    with session_scope() as s:
        runs = [(r.status, r.trigger, r.error, r.finished_at is not None) for r in s.query(Run)]
        briefs = [(b.body_markdown, b.delivered_to) for b in s.query(Brief)]
    return runs, briefs


def test_successful_run_records_ok_and_saves_the_brief(monkeypatch, alerts):
    monkeypatch.setattr(workflow, "graph", FakeGraph({"body": "BRIEF", "delivered_to": "1000"}))

    workflow.run_morning_brief("schedule")

    assert _rows() == ([("ok", "schedule", None, True)], [("BRIEF", "1000")])
    assert alerts == []


def test_graph_crash_marks_the_run_failed_and_pings_telegram(monkeypatch, alerts):
    monkeypatch.setattr(workflow, "graph", FakeGraph(exc=RuntimeError("boom")))

    workflow.run_morning_brief()

    runs, briefs = _rows()
    assert runs == [("error", "manual", "RuntimeError: boom", True)]
    assert briefs == []
    assert len(alerts) == 1 and "RuntimeError: boom" in alerts[0]


def test_undelivered_brief_is_a_failure_but_the_body_is_kept_for_history(monkeypatch, alerts):
    monkeypatch.setattr(
        workflow, "graph", FakeGraph({"body": "", "delivered_to": None, "error": "compose produced empty body"})
    )

    workflow.run_morning_brief()

    runs, _ = _rows()
    assert runs[0][0] == "error" and "compose produced empty body" in runs[0][2]
    assert len(alerts) == 1


def test_a_failing_fallback_ping_does_not_raise(monkeypatch):
    monkeypatch.setattr(workflow, "graph", FakeGraph(exc=RuntimeError("boom")))

    def telegram_down(msg):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(workflow, "send_telegram_message", telegram_down)
    run_id = workflow.run_morning_brief()
    assert isinstance(run_id, int)
