# Database Schema (MVP)

## users

- id (uuid, pk)
- email (text, unique, not null)
- timezone (text, default `UTC`)
- created_at (timestamptz)
- updated_at (timestamptz)

## oauth_tokens

- id (uuid, pk)
- user_id (uuid, fk -> users.id)
- provider (text) - `google`
- access_token (text, encrypted)
- refresh_token (text, encrypted)
- scope (text)
- expires_at (timestamptz)
- created_at (timestamptz)
- updated_at (timestamptz)

## email_messages

- id (uuid, pk)
- user_id (uuid, fk)
- provider_message_id (text, unique)
- provider_thread_id (text)
- from_email (text)
- to_emails (jsonb)
- subject (text)
- snippet (text)
- received_at (timestamptz)
- label_ids (jsonb)
- is_unread (boolean)
- raw_payload (jsonb, optional in MVP)
- created_at (timestamptz)
- updated_at (timestamptz)

## calendar_events

- id (uuid, pk)
- user_id (uuid, fk)
- provider_event_id (text, unique)
- calendar_id (text)
- title (text)
- description (text)
- location (text)
- attendees (jsonb)
- starts_at (timestamptz)
- ends_at (timestamptz)
- created_at (timestamptz)
- updated_at (timestamptz)

## tasks

- id (uuid, pk)
- user_id (uuid, fk)
- source_type (text) - `email` | `calendar`
- source_id (uuid) - email_messages.id or calendar_events.id
- category (text) - Development | Customer | Finance | Marketing | Admin
- action_type (text) - Reply | Pay | Build | Schedule | Review
- urgency (text) - Today | ThisWeek | Later
- title (text)
- details (text)
- due_at (timestamptz)
- priority_score (numeric)
- status (text) - Open | Done | Snoozed
- snoozed_until (date, nullable)
- created_at (timestamptz)
- updated_at (timestamptz)

## daily_briefings

- id (uuid, pk)
- user_id (uuid, fk)
- briefing_date (date)
- content_markdown (text)
- sent_at (timestamptz, nullable)
- created_at (timestamptz)

## Indexes

- tasks(user_id, status, due_at)
- tasks(user_id, priority_score desc)
- email_messages(user_id, received_at desc)
- calendar_events(user_id, starts_at)
- daily_briefings(user_id, briefing_date unique)
