# Hetzner Server Diagram
**IP:** 5.161.104.5 — 2 GB RAM · 38 GB disk · Ubuntu

---

## Network topology

```
                            Internet
                               │
                    ┌──────────┴──────────┐
                    │   nginx (80 / 443)   │
                    │   TLS via Certbot    │
                    │   (Let's Encrypt)    │
                    └──────────┬──────────┘
                               │
           ┌───────────────────┼───────────────────┐
           │                   │                   │
           ▼                   ▼                   ▼
assistant.alphatronex   status.alphatronex   vault.alphatronex
        .com                  .com                .com
           │                   │                   │
           ▼                   ▼                   ▼
    :8000 (Docker)      :3001 (Docker)      :8200 (Docker)
 ┌─────────────────┐  ┌──────────────┐  ┌───────────────────┐
 │ personal-       │  │ uptime-kuma  │  │   vaultwarden     │
 │ assistant       │  │ (monitoring) │  │ (password manager)│
 │ FastAPI/uvicorn │  └──────────────┘  └───────────────────┘
 └────────┬────────┘
          │
          │  on startup, two daemon threads:
          │  • APScheduler  — 08:00 daily brief cron
          │  • TG poller    — Telegram long-poll for WA approvals
          │
          │  POST /whatsapp/incoming
          │◄──────────────────────────────────────────┐
          │                                           │
          │                              :3000 (host process)
          │                         ┌──────────────────────────┐
          │                         │   whatsapp-bridge        │
          │                         │   (Node.js / Baileys)    │
          │                         │   runs directly on host  │
          │                         └────────────┬─────────────┘
          │                                      │
          │                              WhatsApp Web
          │                              (QR-code auth)
          │
          │  LangGraph StateGraph  (/run-now  or  08:00 cron)
          ▼
 ┌─────────────────────────────────────────────┐
 │                                             │
 │   START                                     │
 │     │                                       │
 │     ├──► calendar  ──┐                      │
 │     ├──► gmail     ──┤                      │
 │     ├──► youtube   ──┼──► compose ──► deliver ──► END
 │     └──► reminders ──┘                      │
 │                                             │
 └─────────────────────────────────────────────┘
          │                        │
          ▼                        ▼
    Google APIs              Telegram Bot API
    • Calendar v3            sendMessage
    • Gmail v1               (+ inline keyboards
    • YouTube Data v3          for WA approvals)
          │
          ▼
    OpenAI API (gpt-4o-mini)
    • Gmail summary
    • YouTube TL;DRs
    • WhatsApp reply suggestions
```

---

## Services

| Service | Runtime | Internal port | Public URL |
|---------|---------|--------------|------------|
| personal-assistant | Docker | 8000 | https://assistant.alphatronex.com |
| uptime-kuma | Docker | 3001 | https://status.alphatronex.com |
| vaultwarden | Docker | 8200 | https://vault.alphatronex.com |
| whatsapp-bridge | Node.js (host) | 3000 | internal only (172.17.0.1:3000) |

---

## Persistent storage

```
/opt/assistant/data/
  agentic.db          — SQLite (all tables below)
  token.json          — Google OAuth refresh token
  credentials.json    — Google OAuth client secrets

SQLite tables
  runs              — one row per morning-brief execution
  briefs            — rendered markdown body per run
  reminders         — recurring reminders (managed via /settings)
  seen_items        — dedup log for YouTube videos
  app_settings      — feature flags (gmail_enabled, youtube_enabled)
  youtube_channels  — channel list (managed via /settings)
  pending_replies   — WhatsApp DMs awaiting Telegram approval
```

---

## Outbound traffic

| Destination | Purpose |
|-------------|---------|
| `googleapis.com` | Calendar, Gmail, YouTube Data, OAuth refresh |
| `api.telegram.org` | Delivery + long-poll for WA approvals |
| `api.openai.com` | Gmail summary, YouTube TL;DRs, WA reply suggestions |
| `172.17.0.1:3000` | WhatsApp bridge (Docker → host, local only) |
