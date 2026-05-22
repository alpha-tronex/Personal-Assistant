# Personal Assistant

Personal morning briefing agent — Calendar + Gmail + YouTube → Telegram, daily at 08:00 ET.

- 📐 Architecture & build phases: [`architect.md`](./architect.md)
- 🗓 Week-by-week plan (3–5 hrs/week): [`milestone.md`](./milestone.md)
- 🛠 Setup walkthrough & API: [`backend/README.md`](./backend/README.md)
- ⏰ macOS scheduled job: [`launchd/com.personalassistant.morning.plist`](./launchd/com.personalassistant.morning.plist)
- 📝 Older reference notes (different stack — Postgres/Web OAuth — kept only for occasional reference): [`README/`](./README/). Current setup lives in [`backend/README.md`](./backend/README.md).

Self-hosted, single-user, local-Mac-only Python app. Reads Google Calendar /
Gmail / YouTube and delivers a daily summary via a Telegram bot.
