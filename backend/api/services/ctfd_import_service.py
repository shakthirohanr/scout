"""CTFd import service: authenticate, download challenges, persist catalog."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
import yaml
from markdownify import markdownify as html_to_markdown

from backend.api.database import session_scope
from backend.api.repositories.ctf_repository import (
    get_or_create_ctf_source,
    replace_challenge_files,
    set_import_status,
    slugify,
    upsert_challenge,
)
from backend.api.services.mappers import ctf_source_to_dict
from backend.api.schemas import CTFImportRequest, CTFImportResponse


NONCE_PATTERNS = (
    re.compile(r'id="nonce"[^>]*value="([^"]+)"'),
    re.compile(r'name="nonce"[^>]*value="([^"]+)"'),
)


class CTFImportError(RuntimeError):
    pass


@dataclass(slots=True)
class DownloadedFile:
    filename: str
    source_url: str
    local_path: str
    size_bytes: int


class CTFdImportClient:
    def __init__(
        self,
        *,
        base_url: str,
        auth_mode: str,
        token: str,
        username: str,
        password: str,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_mode = auth_mode
        self.token = token.strip()
        self.username = username.strip()
        self.password = password
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            follow_redirects=False,
            verify=False,
            timeout=45.0,
            headers={"User-Agent": "ctf-agent-importer/1.0"},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _verify_token(self) -> None:
        response = await self._client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Token {self.token}"},
        )
        if response.status_code != 200:
            raise CTFImportError("Token authentication failed against /api/v1/users/me.")

    async def _login_with_credentials(self) -> None:
        response = await self._client.get("/login")
        nonce = ""
        for pattern in NONCE_PATTERNS:
            match = pattern.search(response.text)
            if match:
                nonce = match.group(1)
                break
        if not nonce:
            raise CTFImportError("Unable to find CTFd login nonce.")

        response = await self._client.post(
            "/login",
            data={
                "name": self.username,
                "password": self.password,
                "_submit": "Submit",
                "nonce": nonce,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code == 200:
            raise CTFImportError("Credential login failed. Check username/password.")

    async def authenticate(self) -> None:
        if self.auth_mode == "token":
            await self._verify_token()
            return
        await self._login_with_credentials()

    def _api_headers(self) -> dict[str, str]:
        if self.auth_mode == "token":
            return {"Authorization": f"Token {self.token}", "Content-Type": "application/json"}
        return {"Content-Type": "application/json"}

    async def _get_json(self, path: str) -> dict[str, Any]:
        response = await self._client.get(path, headers=self._api_headers())
        if response.status_code != 200:
            raise CTFImportError(f"CTFd API call failed: GET {path} ({response.status_code})")
        payload = response.json()
        if isinstance(payload, dict) and payload.get("success") is False:
            raise CTFImportError(f"CTFd API returned unsuccessful response for {path}")
        return payload

    async def fetch_all_challenges(self) -> list[dict[str, Any]]:
        stubs_payload = await self._get_json("/api/v1/challenges?per_page=500")
        stubs = [item for item in stubs_payload.get("data", []) if item.get("type") != "hidden"]

        challenges: list[dict[str, Any]] = []
        for stub in stubs:
            challenge_id = stub.get("id")
            if challenge_id is None:
                continue
            detail_payload = await self._get_json(f"/api/v1/challenges/{challenge_id}")
            detail = detail_payload.get("data")
            if isinstance(detail, dict):
                challenges.append(detail)
        return challenges

    async def download_files(
        self,
        file_urls: list[str],
        challenge_dir: Path,
    ) -> list[DownloadedFile]:
        dist_dir = challenge_dir / "distfiles"
        downloaded: list[DownloadedFile] = []

        if not file_urls:
            return downloaded

        dist_dir.mkdir(parents=True, exist_ok=True)
        for raw_url in file_urls:
            absolute_url = urljoin(f"{self.base_url}/", raw_url)
            response = await self._client.get(absolute_url, headers=self._api_headers())
            if response.status_code != 200:
                continue

            filename = Path(raw_url).name or "file"
            local_path = dist_dir / filename
            local_path.write_bytes(response.content)
            downloaded.append(
                DownloadedFile(
                    filename=filename,
                    source_url=absolute_url,
                    local_path=str(local_path),
                    size_bytes=len(response.content),
                )
            )

        return downloaded


def _markdown_description(raw_html: str) -> str:
    if not raw_html:
        return ""
    markdown = html_to_markdown(raw_html, heading_style="atx")
    return re.sub(r"\n{3,}", "\n\n", markdown).strip()


def _metadata_payload(challenge: dict[str, Any]) -> dict[str, Any]:
    tags_raw = challenge.get("tags") or []
    tags: list[str] = []
    for item in tags_raw:
        if isinstance(item, dict):
            val = item.get("value")
            if isinstance(val, str) and val.strip():
                tags.append(val.strip())
        elif isinstance(item, str) and item.strip():
            tags.append(item.strip())

    payload: dict[str, Any] = {
        "version": "beta1",
        "name": challenge.get("name") or "Unknown",
        "category": challenge.get("category") or "",
        "description": _markdown_description(str(challenge.get("description") or "")),
        "value": int(challenge.get("value") or 0),
        "solves": int(challenge.get("solves") or 0),
    }

    connection_info = str(challenge.get("connection_info") or "").strip()
    if connection_info:
        payload["connection_info"] = connection_info
    if tags:
        payload["tags"] = tags

    return payload


async def import_ctf_challenges(request: CTFImportRequest) -> CTFImportResponse:
    client = CTFdImportClient(
        base_url=request.ctfd_url,
        auth_mode=request.auth_mode,
        token=request.token,
        username=request.username,
        password=request.password,
    )

    try:
        await client.authenticate()

        root = Path(request.challenges_root).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)

        with session_scope() as session:
            ctf_source = get_or_create_ctf_source(
                session,
                name=request.name,
                base_url=request.ctfd_url,
                auth_mode=request.auth_mode,
                challenges_root=str(root),
            )
            ctf_root = root / ctf_source.slug
            ctf_root.mkdir(parents=True, exist_ok=True)
            set_import_status(session, ctf_source, status="running")

        challenge_details = await client.fetch_all_challenges()
        imported_count = 0
        downloaded_files = 0
        prepared: list[dict[str, Any]] = []

        with session_scope() as session:
            source = get_or_create_ctf_source(
                session,
                name=request.name,
                base_url=request.ctfd_url,
                auth_mode=request.auth_mode,
                challenges_root=str(root),
            )
            ctf_slug = source.slug

        ctf_root = root / ctf_slug
        ctf_root.mkdir(parents=True, exist_ok=True)

        for challenge_data in challenge_details:
            challenge_name = str(challenge_data.get("name") or "challenge")
            challenge_slug = slugify(challenge_name)
            challenge_dir = ctf_root / challenge_slug
            challenge_dir.mkdir(parents=True, exist_ok=True)

            downloaded = await client.download_files(
                list(challenge_data.get("files") or []),
                challenge_dir,
            )
            downloaded_files += len(downloaded)

            metadata = _metadata_payload(challenge_data)
            metadata_path = challenge_dir / "metadata.yml"
            metadata_path.write_text(
                yaml.dump(metadata, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )

            prepared.append(
                {
                    "challenge_data": challenge_data,
                    "challenge_name": challenge_name,
                    "challenge_slug": challenge_slug,
                    "challenge_dir": str(challenge_dir),
                    "metadata": metadata,
                    "downloaded": downloaded,
                }
            )

        with session_scope() as session:
            ctf_source = get_or_create_ctf_source(
                session,
                name=request.name,
                base_url=request.ctfd_url,
                auth_mode=request.auth_mode,
                challenges_root=str(root),
            )

            for item in prepared:
                challenge_data = item["challenge_data"]
                downloaded = item["downloaded"]

                challenge_record = upsert_challenge(
                    session,
                    source=ctf_source,
                    external_id=(
                        int(challenge_data["id"]) if challenge_data.get("id") is not None else None
                    ),
                    name=str(item["challenge_name"]),
                    challenge_slug=str(item["challenge_slug"]),
                    path=str(item["challenge_dir"]),
                    category=str(challenge_data.get("category") or ""),
                    value=int(challenge_data.get("value") or 0),
                    description=str(item["metadata"].get("description") or ""),
                    connection_info=str(challenge_data.get("connection_info") or ""),
                    has_distfiles=len(downloaded) > 0,
                    distfile_count=len(downloaded),
                    solves=int(challenge_data.get("solves") or 0),
                )

                replace_challenge_files(
                    session,
                    challenge=challenge_record,
                    files=[
                        {
                            "filename": file_item.filename,
                            "source_url": file_item.source_url,
                            "local_path": file_item.local_path,
                            "size_bytes": file_item.size_bytes,
                        }
                        for file_item in downloaded
                    ],
                )
                imported_count += 1

            set_import_status(session, ctf_source, status="success")
            source_summary = ctf_source_to_dict(ctf_source, challenge_count=imported_count)

        from datetime import datetime, timezone

        return CTFImportResponse(
            ctf=source_summary,
            imported_challenges=imported_count,
            downloaded_files=downloaded_files,
            root_directory=str((Path(root) / str(source_summary["slug"])).resolve()),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        with session_scope() as session:
            source = get_or_create_ctf_source(
                session,
                name=request.name,
                base_url=request.ctfd_url,
                auth_mode=request.auth_mode,
                challenges_root=str(Path(request.challenges_root).expanduser().resolve()),
            )
            set_import_status(session, source, status="failed", error=str(exc))
        raise
    finally:
        await client.close()
