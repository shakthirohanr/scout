"""Relational schema for CTF sources, challenges, files, and solver runs."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.api.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class CTFSource(Base):
    __tablename__ = "ctf_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    base_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    auth_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="token")
    challenges_root: Mapped[str] = mapped_column(String(1024), nullable=False)

    last_import_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_import_status: Mapped[str] = mapped_column(String(32), nullable=False, default="never")
    last_import_error: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    challenges: Mapped[list[Challenge]] = relationship(
        "Challenge",
        back_populates="ctf_source",
        cascade="all, delete-orphan",
    )


class Challenge(Base):
    __tablename__ = "challenges"
    __table_args__ = (
        UniqueConstraint("ctf_id", "external_id", name="uq_challenge_ctf_external_id"),
        UniqueConstraint("ctf_id", "slug", name="uq_challenge_ctf_slug"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ctf_id: Mapped[int] = mapped_column(ForeignKey("ctf_sources.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    name: Mapped[str] = mapped_column(String(512), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(2048), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    connection_info: Mapped[str] = mapped_column(Text, nullable=False, default="")

    has_distfiles: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    distfile_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    solves: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    latest_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latest_flag: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_log_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    latest_trace_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    steering_log_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    ctf_source: Mapped[CTFSource] = relationship("CTFSource", back_populates="challenges")
    files: Mapped[list[ChallengeFile]] = relationship(
        "ChallengeFile",
        back_populates="challenge",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list[SolverRun]] = relationship("SolverRun", back_populates="challenge")


class ChallengeFile(Base):
    __tablename__ = "challenge_files"
    __table_args__ = (UniqueConstraint("challenge_id", "filename", name="uq_challenge_file_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    challenge_id: Mapped[str] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    local_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    challenge: Mapped[Challenge] = relationship("Challenge", back_populates="files")


class SolverRun(Base):
    __tablename__ = "solver_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    challenge_id: Mapped[str | None] = mapped_column(
        ForeignKey("challenges.id", ondelete="SET NULL"), nullable=True
    )
    mode: Mapped[str] = mapped_column(String(64), nullable=False, default="solve")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="starting")
    command_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    workdir: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_log_path: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    steering_log_path: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    flag: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_trace_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trace_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    challenge: Mapped[Challenge | None] = relationship("Challenge", back_populates="runs")
