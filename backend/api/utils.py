"""Shared utility functions for the backend API."""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = ["utcnow", "utcnow_iso"]


def utcnow() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(UTC)


def utcnow_iso() -> str:
    """Return the current time in UTC as an ISO 8601 string."""
    return utcnow().isoformat()
