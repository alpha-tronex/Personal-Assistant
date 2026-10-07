from __future__ import annotations

from app import graph as g


def _stub_sections(monkeypatch, **overrides):
    defaults = {
        "summarize_today_calendar": lambda: "CAL",
        "summarize_gmail": lambda: "MAIL",
        "summarize_youtube_uploads": lambda: "YT",
        "summarize_reminders": lambda: "",
    }
    defaults.update(overrides)
    for name, fn in defaults.items():
        monkeypatch.setattr(g, name, fn)


def test_safe_section_turns_an_exception_into_a_visible_placeholder():
    def boom():
        raise TimeoutError("gmail slow")

    assert g._safe_section("gmail", boom) == "_(section failed: TimeoutError: gmail slow)_"


def test_full_graph_composes_every_section_and_delivers_once(monkeypatch):
    _stub_sections(monkeypatch)
    delivered = []
    monkeypatch.setattr(g, "send_telegram_message", lambda body: delivered.append(body) or "1000")

    result = g.build_graph().invoke({})

    assert result["delivered_to"] == "1000"
    assert len(delivered) == 1
    for part in ("CAL", "MAIL", "YT"):
        assert part in delivered[0]


def test_one_failing_source_does_not_stop_the_brief(monkeypatch):
    def boom():
        raise RuntimeError("youtube down")

    _stub_sections(monkeypatch, summarize_youtube_uploads=boom)
    monkeypatch.setattr(g, "send_telegram_message", lambda body: "1000")

    result = g.build_graph().invoke({})

    assert "_(section failed: RuntimeError: youtube down)_" in result["body"]
    assert result["delivered_to"] == "1000"


def test_deliver_node_refuses_to_send_an_empty_body(monkeypatch):
    monkeypatch.setattr(g, "send_telegram_message", lambda body: (_ for _ in ()).throw(AssertionError("sent")))
    assert g.deliver_node({"body": ""}) == {"delivered_to": None, "error": "compose produced empty body"}
