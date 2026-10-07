# Backend tests

```bash
cd backend
pip install -e ".[dev]"
ruff check .
pytest                                # ~10 s, no network, no real credentials
bash scripts/testability-audit.sh     # hard checks fail CI; advisory = known debt
```

CI runs exactly these on every push and pull request (`.github/workflows/ci.yml`);
`main` only deploys when they all pass.

## How the suite stays hermetic

`conftest.py` sets up three guarantees before anything under `app` is imported:

- **Settings:** test values come from env vars, and `backend/.env` is never read,
  so your real tokens can't leak into a run.
- **Database:** every test starts with empty tables in a throwaway SQLite file.
- **Network:** `socket.connect`/`getaddrinfo` raise `NetworkBlocked`. A test
  that reaches for Telegram, OpenAI, Google or the bridge fails instead of
  silently calling them.

The `client` fixture is a `TestClient` *without* the app lifespan. Entering it
(`with TestClient(app)`) would start the 08:00 scheduler and the Telegram
long-poll thread, so the audit fails CI if a test does that.

## Layers and their seams

Each layer is tested by mocking exactly one thing: the layer below it.

| Layer | Path | Test mocks | Example |
|---|---|---|---|
| Tool (network I/O) | `app/tools/` | `httpx.Client` via `httpx.MockTransport`, or a fake Google service object | `tools/test_telegram.py`, `tools/test_youtube.py` |
| Agent (brief sections, LLM calls) | `app/agents/` | the tool function, plus `_llm_summarize` / `_summarize_video` for the LLM call | `agents/test_gmail_agent.py` |
| Graph / workflow | `app/graph.py`, `app/workflow.py` | the agent functions / the compiled graph | `test_graph.py`, `test_workflow.py` |
| HTTP API | `app/main.py`, `app/routers/` | the agent or tool the route calls | `test_main.py`, `routers/` |
| Telegram poller | `app/telegram_poller.py` | `answer_callback_query`, `_send_text`, `send_whatsapp_message` | `test_telegram_poller.py` |

Patch names where they're **used**, not where they're defined
(`monkeypatch.setattr(gmail_agent, "fetch_recent_messages", ...)`), because
modules import functions by name.

## Rules (enforced by `scripts/testability-audit.sh`)

**Hard (CI fails):**

- **A1:** `ChatOpenAI` is only constructed in `app/agents/`.
- **A2:** Google API clients (`build(...)`) are only created in `app/tools/`.
- **A3:** config comes from `get_settings()`, never `os.environ` / `os.getenv`.
- **T1:** tests never enter the app lifespan.
- **T2:** no real `time.sleep` in tests.

**Advisory (known debt, listed in every CI summary):**

- **A4:** raw `httpx` outside `app/tools/` (the poller and the projects
  dashboard's GitHub fetch).
- **A5:** hidden clock (`datetime.now()`, `time.time()`) in agents and routers.
  Tests freeze it by patching the module's `datetime` (see
  `agents/test_reminders_agent.py`). New code should take `now` as a parameter.
- **A6:** `get_settings()` called at import time (`db.py`, `main.py`).
- **A7:** a module under `app/` that no test imports. To exempt one, add
  `# @testability-exempt: <reason>`.

When an advisory check reaches zero findings, move it to the hard section of
the script.

## Writing a new test

- Every new module under `app/` ships with a test in the same change.
- Name tests after the behaviour and why it matters, e.g.
  `test_paused_channels_are_not_fetched`, not `test_load_channels`.
- Use real model/dataclass fixtures (`GmailMessage(...)`, `PendingReply(...)`)
  so a schema change breaks the test.
- Cover the failure path too: every agent turns an exception into a visible
  `_(failed: …)_` placeholder, and the tests check that it does.
