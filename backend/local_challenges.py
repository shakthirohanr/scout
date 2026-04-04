"""Helpers for discovering local challenge directories and metadata."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.prompts import ChallengeMeta


def local_challenge_dirs(root: str) -> list[Path]:
    """Return challenge directories containing a metadata.yml file."""
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists():
        return []

    meta_path = root_path / "metadata.yml"
    if meta_path.exists():
        return [root_path]

    seen: set[Path] = set()
    challenge_dirs: list[Path] = []
    for path in sorted(root_path.rglob("metadata.yml")):
        challenge_dir = path.parent.resolve()
        if challenge_dir not in seen:
            seen.add(challenge_dir)
            challenge_dirs.append(challenge_dir)
    return challenge_dirs


@dataclass(slots=True)
class LocalChallengeSummary:
    name: str
    path: str
    category: str
    value: int
    description: str
    connection_info: str
    has_distfiles: bool
    distfile_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def list_local_challenges(root: str) -> list[LocalChallengeSummary]:
    """Read challenge metadata under a root directory."""
    summaries: list[LocalChallengeSummary] = []
    for challenge_dir in local_challenge_dirs(root):
        meta = ChallengeMeta.from_yaml(challenge_dir / "metadata.yml")
        distfiles_dir = challenge_dir / "distfiles"
        distfile_count = (
            len([entry for entry in distfiles_dir.iterdir() if entry.is_file()])
            if distfiles_dir.exists()
            else 0
        )
        summaries.append(
            LocalChallengeSummary(
                name=meta.name,
                path=str(challenge_dir),
                category=meta.category,
                value=meta.value,
                description=meta.description,
                connection_info=meta.connection_info,
                has_distfiles=distfile_count > 0,
                distfile_count=distfile_count,
            )
        )
    return summaries
