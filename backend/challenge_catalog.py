"""Challenge catalog persistence (Postgres) and runtime fallback."""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from backend.config import Settings
from backend.local_challenges import LocalChallengeSummary, list_local_challenges

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - optional dependency fallback
    psycopg = None
    dict_row = None


@dataclass(slots=True)
class ChallengeCatalogItem:
    id: str
    name: str
    path: str
    category: str
    value: int
    description: str
    connection_info: str
    has_distfiles: bool
    distfile_count: int
    started_at: str | None
    updated_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_fallback_catalog: dict[str, ChallengeCatalogItem] = {}
_fallback_name_index: dict[str, str] = {}
_warned_fallback = False


def _warn(reason: str) -> None:
    global _warned_fallback
    if _warned_fallback:
        return
    _warned_fallback = True
    print(
        f"[challenge_catalog] Using in-memory fallback ({reason}). "
        "Set POSTGRES_URL and install psycopg for persistence."
    )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_url(settings: Settings) -> str | None:
    return settings.postgres_url or settings.database_url or None


def _connect(settings: Settings):
    if psycopg is None:
        return None
    db_url = _db_url(settings)
    if not db_url:
        return None
    return psycopg.connect(db_url, autocommit=True, row_factory=dict_row)


def _ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS challenge_catalog (
          challenge_id TEXT PRIMARY KEY,
          challenge_name TEXT NOT NULL UNIQUE,
          challenge_path TEXT NOT NULL,
          category TEXT NOT NULL DEFAULT '',
          value INTEGER NOT NULL DEFAULT 0,
          description TEXT NOT NULL DEFAULT '',
          connection_info TEXT NOT NULL DEFAULT '',
          has_distfiles BOOLEAN NOT NULL DEFAULT FALSE,
          distfile_count INTEGER NOT NULL DEFAULT 0,
          started_at TIMESTAMPTZ NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _to_item(row: dict[str, Any]) -> ChallengeCatalogItem:
    return ChallengeCatalogItem(
        id=str(row["challenge_id"]),
        name=str(row["challenge_name"]),
        path=str(row["challenge_path"]),
        category=str(row.get("category") or ""),
        value=int(row.get("value") or 0),
        description=str(row.get("description") or ""),
        connection_info=str(row.get("connection_info") or ""),
        has_distfiles=bool(row.get("has_distfiles")),
        distfile_count=int(row.get("distfile_count") or 0),
        started_at=row.get("started_at").isoformat() if row.get("started_at") else None,
        updated_at=row.get("updated_at").isoformat() if row.get("updated_at") else None,
    )


def _fallback_id(name: str) -> str:
    if name in _fallback_name_index:
        return _fallback_name_index[name]
    challenge_id = secrets.token_urlsafe(9)
    _fallback_name_index[name] = challenge_id
    return challenge_id


def _sync_fallback(challenges: list[LocalChallengeSummary]) -> list[ChallengeCatalogItem]:
    now = _utcnow_iso()
    result: list[ChallengeCatalogItem] = []
    for challenge in challenges:
        challenge_id = _fallback_id(challenge.name)
        previous = _fallback_catalog.get(challenge_id)
        item = ChallengeCatalogItem(
            id=challenge_id,
            name=challenge.name,
            path=challenge.path,
            category=challenge.category,
            value=challenge.value,
            description=challenge.description,
            connection_info=challenge.connection_info,
            has_distfiles=challenge.has_distfiles,
            distfile_count=challenge.distfile_count,
            started_at=previous.started_at if previous else None,
            updated_at=now,
        )
        _fallback_catalog[challenge_id] = item
        result.append(item)

    return sorted(result, key=lambda item: item.name.lower())


def sync_challenge_catalog(challenges_root: str, settings: Settings) -> list[ChallengeCatalogItem]:
    challenges = list_local_challenges(challenges_root)
    conn = None
    try:
        conn = _connect(settings)
        if conn is None:
            _warn("POSTGRES_URL or DATABASE_URL missing, or psycopg unavailable")
            return _sync_fallback(challenges)

        _ensure_schema(conn)
        for challenge in challenges:
            existing = conn.execute(
                """
                SELECT challenge_id
                FROM challenge_catalog
                WHERE challenge_name = %s
                LIMIT 1
                """,
                [challenge.name],
            ).fetchone()

            challenge_id = str(existing["challenge_id"]) if existing else secrets.token_urlsafe(9)
            conn.execute(
                """
                INSERT INTO challenge_catalog (
                  challenge_id, challenge_name, challenge_path, category, value,
                  description, connection_info, has_distfiles, distfile_count, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (challenge_name)
                DO UPDATE SET
                  challenge_path = EXCLUDED.challenge_path,
                  category = EXCLUDED.category,
                  value = EXCLUDED.value,
                  description = EXCLUDED.description,
                  connection_info = EXCLUDED.connection_info,
                  has_distfiles = EXCLUDED.has_distfiles,
                  distfile_count = EXCLUDED.distfile_count,
                  updated_at = NOW()
                """,
                [
                    challenge_id,
                    challenge.name,
                    challenge.path,
                    challenge.category,
                    challenge.value,
                    challenge.description,
                    challenge.connection_info,
                    challenge.has_distfiles,
                    challenge.distfile_count,
                ],
            )

        rows = conn.execute(
            """
            SELECT
              challenge_id, challenge_name, challenge_path, category, value,
              description, connection_info, has_distfiles, distfile_count,
              started_at, updated_at
            FROM challenge_catalog
            ORDER BY challenge_name ASC
            """
        ).fetchall()

        return [_to_item(row) for row in rows]
    except Exception as exc:
        _warn(str(exc))
        return _sync_fallback(challenges)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_challenge_by_id(
    challenge_id: str,
    challenges_root: str,
    settings: Settings,
) -> ChallengeCatalogItem | None:
    catalog = sync_challenge_catalog(challenges_root, settings)
    for item in catalog:
        if item.id == challenge_id:
            return item
    return None


def mark_challenge_started(
    challenge_id: str,
    challenges_root: str,
    settings: Settings,
) -> ChallengeCatalogItem | None:
    conn = None
    try:
        conn = _connect(settings)
        if conn is None:
            item = get_challenge_by_id(challenge_id, challenges_root, settings)
            if not item:
                return None
            now = _utcnow_iso()
            updated = ChallengeCatalogItem(
                id=item.id,
                name=item.name,
                path=item.path,
                category=item.category,
                value=item.value,
                description=item.description,
                connection_info=item.connection_info,
                has_distfiles=item.has_distfiles,
                distfile_count=item.distfile_count,
                started_at=now,
                updated_at=now,
            )
            _fallback_catalog[challenge_id] = updated
            return updated

        _ensure_schema(conn)
        row = conn.execute(
            """
            UPDATE challenge_catalog
            SET started_at = NOW(), updated_at = NOW()
            WHERE challenge_id = %s
            RETURNING
              challenge_id, challenge_name, challenge_path, category, value,
              description, connection_info, has_distfiles, distfile_count,
              started_at, updated_at
            """,
            [challenge_id],
        ).fetchone()
        if row:
            return _to_item(row)
    except Exception as exc:
        _warn(str(exc))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    return get_challenge_by_id(challenge_id, challenges_root, settings)
