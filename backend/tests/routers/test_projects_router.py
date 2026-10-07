from __future__ import annotations

import pytest
import yaml

from app.routers import projects


@pytest.fixture
def projects_file(tmp_path, monkeypatch):
    path = tmp_path / "projects.yaml"
    path.write_text(yaml.dump({"projects": [
        {"name": "Quiz Master", "tagline": "<quiz>", "done": ["a", "b", "c"], "todo": ["d"], "repos": ["me/quiz"]},
    ]}))
    monkeypatch.setattr(projects, "PROJECTS_FILE", path)
    return path


@pytest.fixture
def github(monkeypatch):
    def fake(repo):
        return {"message": "Fix <bug>", "date": "2026-10-01T00:00:00Z", "sha": "abc1234", "days": 3, "repo": repo}

    monkeypatch.setattr(projects, "_fetch_latest_commit", fake)


@pytest.mark.parametrize(("days", "text"), [(0, "today"), (1, "1 day ago"), (12, "12 days ago"), (30, "1 month ago"), (95, "3 months ago")])
def test_fmt_relative(days, text):
    assert projects._fmt_relative(days) == text


@pytest.mark.parametrize(("days", "label"), [(7, "Active"), (8, "Recent"), (30, "Recent"), (90, "Slow"), (91, "Dormant")])
def test_freshness_buckets(days, label):
    assert projects._freshness(days)[1] == label


def test_dashboard_renders_escaped_cards_with_progress(client, projects_file, github):
    page = client.get("/projects").text
    assert "Quiz Master" in page and "75%" in page
    assert "&lt;quiz&gt;" in page and "Fix &lt;bug&gt;" in page
    assert "<quiz>" not in page


def test_dashboard_survives_github_being_down(client, projects_file, monkeypatch):
    def down(repo):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(projects, "_fetch_latest_commit", down)
    page = client.get("/projects")
    assert page.status_code == 200 and "unavailable" in page.text


def test_update_project_saves_trimmed_items_case_insensitively(client, projects_file):
    r = client.patch("/projects/quiz master", json={"done": [" a ", ""], "todo": ["z"]})
    assert r.json() == {"ok": True}
    saved = yaml.safe_load(projects_file.read_text())["projects"][0]
    assert (saved["done"], saved["todo"], saved["tagline"]) == (["a"], ["z"], "<quiz>")


def test_update_unknown_project_is_404(client, projects_file):
    assert client.patch("/projects/nope", json={"done": [], "todo": []}).status_code == 404


def test_commits_endpoint(client, projects_file, github):
    r = client.get("/projects/Quiz Master/commits")
    assert r.status_code == 200
    assert "abc1234" in r.text
