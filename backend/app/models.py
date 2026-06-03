"""SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Run(Base):
    """One execution of the morning-brief workflow."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    trigger: Mapped[str] = mapped_column(String(32), default="manual")  # "manual" | "schedule"
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Brief(Base):
    """The actual rendered brief produced by a run."""

    __tablename__ = "briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    body_markdown: Mapped[str] = mapped_column(Text, default="")
    delivered_to: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Reminder(Base):
    """A user-defined recurring reminder included in the morning brief."""

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(255))
    frequency: Mapped[str] = mapped_column(String(16))          # "daily" | "weekly" | "monthly"
    day_of_week: Mapped[str | None] = mapped_column(String(16), nullable=True)   # "monday" … "sunday"
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)     # 1–31
    time: Mapped[str | None] = mapped_column(String(5), nullable=True)           # "HH:MM"
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PendingReply(Base):
    """A WhatsApp message awaiting the user's approval before a reply is sent."""

    __tablename__ = "pending_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wa_from: Mapped[str] = mapped_column(String(64))                           # e.g. "15551234567@c.us"
    contact_name: Mapped[str] = mapped_column(String(128))
    wa_message_id: Mapped[str] = mapped_column(String(255), unique=True)       # dedup
    incoming_body: Mapped[str] = mapped_column(Text)
    suggested_reply: Mapped[str] = mapped_column(Text)
    sent_reply: Mapped[str | None] = mapped_column(Text, nullable=True)        # what was actually sent
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|sent|dismissed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SeenItem(Base):
    """Dedup table so we don't re-summarize a video / email twice."""

    __tablename__ = "seen_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # "video" | "email"
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
