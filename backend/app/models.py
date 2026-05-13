"""SQLAlchemy models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
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


class SeenItem(Base):
    """Dedup table so we don't re-summarize a video / email twice."""

    __tablename__ = "seen_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # "video" | "email"
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
