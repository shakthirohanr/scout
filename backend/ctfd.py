"""CTFd client — async httpx, token + session auth."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36"


@dataclass
class SubmitResult:
    status: str  # "correct" | "already_solved" | "incorrect" | "unknown"
    message: str
    display: str


@dataclass
class CTFdClient:
    base_url: str | None = "http://localhost:8000"
    token: str = ""
    username: str = "admin"
    password: str = "admin"

    _client: httpx.AsyncClient | None = field(default=None, repr=False)
    _csrf_token: str = ""
    _logged_in: bool = False
    _challenge_ids: dict[str, int] = field(default_factory=dict)

    @property
    def is_mock(self) -> bool:
        return not self.base_url

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self.is_mock:
            raise RuntimeError("CTFdClient is in mock mode (no URL configured).")

        if self._client is None:
            # verify=False: CTFd instances often use self-signed certs or HTTP.
            # This is a CTF tool, not production infrastructure.
            self._client = httpx.AsyncClient(
                base_url=(self.base_url or "").rstrip("/"),
                follow_redirects=False,
                verify=False,
                timeout=30.0,
                headers={"User-Agent": USER_AGENT},
            )
        return self._client

    async def _ensure_logged_in(self) -> None:
        if self.is_mock:
            return

        if self._logged_in or self.token:
            return
        client = await self._ensure_client()

        # GET login page for nonce
        resp = await client.get("/login")
        m = re.search(r'id="nonce"[^>]*value="([^"]+)"', resp.text)
        if not m:
            m = re.search(r'name="nonce"[^>]*value="([^"]+)"', resp.text)
        if not m:
            raise RuntimeError("Could not find nonce on CTFd login page")
        nonce = m.group(1)

        # POST credentials
        resp = await client.post(
            "/login",
            data={
                "name": self.username,
                "password": self.password,
                "_submit": "Submit",
                "nonce": nonce,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code == 200:
            raise RuntimeError("CTFd login failed — bad credentials")
        self._logged_in = True

    async def _get_csrf(self) -> str:
        if self._csrf_token:
            return self._csrf_token
        client = await self._ensure_client()
        resp = await client.get("/challenges")
        m = re.search(r"csrfNonce':\s*\"([A-Fa-f0-9]+)\"", resp.text)
        if not m:
            raise RuntimeError("Could not find csrfNonce on CTFd challenges page")
        self._csrf_token = m.group(1)
        return self._csrf_token

    def _base_headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Token {self.token}"
        return h

    async def _get(self, path: str) -> Any:
        await self._ensure_logged_in()
        client = await self._ensure_client()
        resp = await client.get(f"/api/v1{path}", headers=self._base_headers())
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        await self._ensure_logged_in()
        client = await self._ensure_client()
        headers = self._base_headers()
        if not self.token:
            headers["CSRF-Token"] = await self._get_csrf()
        resp = await client.post(
            f"/api/v1{path}",
            json=body,
            headers=headers,
        )
        # Retry once on 403 — CSRF token may have gone stale
        if resp.status_code == 403 and not self.token:
            self._csrf_token = ""
            headers["CSRF-Token"] = await self._get_csrf()
            resp = await client.post(
                f"/api/v1{path}",
                json=body,
                headers=headers,
            )
        resp.raise_for_status()
        return resp.json()

    async def fetch_challenge_stubs(self) -> list[dict[str, Any]]:
        """Fetch lightweight challenge list (no per-challenge detail fetch)."""
        data = await self._get("/challenges?per_page=500")
        return [ch for ch in data.get("data", []) if ch.get("type") != "hidden"]

    async def get_challenge_id(self, name: str) -> int:
        if self.is_mock:
            return 1337

        if name in self._challenge_ids:
            return self._challenge_ids[name]

        data = await self._get("/challenges?per_page=500")
        for ch in data.get("data", []):
            self._challenge_ids[ch["name"]] = ch["id"]

        if name not in self._challenge_ids:
            raise RuntimeError(f'Challenge "{name}" not found in CTFd')
        return self._challenge_ids[name]

    async def submit_flag(self, challenge_name: str, flag: str) -> SubmitResult:
        if self.is_mock:
            print(f"\n[MOCK] Submitting flag for {challenge_name}: {flag}")
            # In mock mode, we assume the user checks the flag. 
            # We return 'unknown' so the solver doesn't automatically stop unless it's designed to stop on unknown.
            # But usually 'correct' stops the solver. 
            # Let's return a special status or just log it. 
            # If we return 'correct', the loop terminates. This is probably desired if the tool found a flag.
            return SubmitResult("correct", "Flag submitted (Mock)", f"MOCK SUBMISSION: {flag}")

        challenge_id = await self.get_challenge_id(challenge_name)
        resp = await self._post(
            "/challenges/attempt",
            {"challenge_id": challenge_id, "submission": flag},
        )
        status = resp.get("data", {}).get("status", "unknown")
        message = resp.get("data", {}).get("message", "")

        if status == "correct":
            return SubmitResult("correct", message, f'CORRECT — "{flag}" accepted. {message}'.strip())
        if status == "already_solved":
            return SubmitResult(
                "already_solved", message, f'ALREADY SOLVED — "{flag}" accepted. {message}'.strip()
            )
        if status == "incorrect":
            return SubmitResult(
                "incorrect", message, f'INCORRECT — "{flag}" rejected. {message}'.strip()
            )
        return SubmitResult("unknown", message, f"Unknown status: {status}")

    async def fetch_all_challenges(self) -> list[dict[str, Any]]:
        data = await self._get("/challenges?per_page=500")
        challenges = []
        for stub in data.get("data", []):
            if stub.get("type") == "hidden":
                continue
            detail = await self._get(f"/challenges/{stub['id']}")
            challenges.append(detail["data"])
        return challenges

    async def fetch_solved_names(self) -> set[str]:
        try:
            me = await self._get("/users/me")
            user_data = me.get("data", {})
            # Use team solves if on a team, otherwise user solves
            team_id = user_data.get("team_id")
            if team_id:
                solves = await self._get(f"/teams/{team_id}/solves")
            else:
                user_id = user_data.get("id")
                if not user_id:
                    return set()
                solves = await self._get(f"/users/{user_id}/solves")
            return {
                s["challenge"]["name"]
                for s in solves.get("data", [])
                if s.get("challenge", {}).get("name")
            }
        except Exception:
            logger.warning("Could not fetch solved challenges", exc_info=True)
            return set()

    @staticmethod
    def _extract_connection_info(payload: Any) -> str:
        """Best-effort extraction of instance connection info from API payloads."""
        if isinstance(payload, str):
            return payload.strip()
        if not isinstance(payload, dict):
            return ""

        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        if not isinstance(data, dict):
            return ""

        for key in ("connection_info", "connection", "url", "link", "instance_url"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

        host = data.get("host")
        port = data.get("port")
        if isinstance(host, str) and host.strip() and port is not None:
            return f"nc {host.strip()} {port}"

        nested = data.get("instance")
        if isinstance(nested, dict):
            for key in ("connection_info", "connection", "url", "link", "instance_url"):
                val = nested.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
            host = nested.get("host")
            port = nested.get("port")
            if isinstance(host, str) and host.strip() and port is not None:
                return f"nc {host.strip()} {port}"

        return ""

    async def _try_start_instance(self, challenge_id: int) -> str:
        """Try common CTFd instance endpoints. Returns connection info if discovered."""
        await self._ensure_logged_in()
        client = await self._ensure_client()
        headers = self._base_headers()
        if not self.token:
            headers["CSRF-Token"] = await self._get_csrf()

        attempts: list[tuple[str, str, dict[str, Any] | None]] = [
            ("POST", f"/api/v1/challenges/{challenge_id}/attempt", {"challenge_id": challenge_id}),
            ("POST", f"/api/v1/challenges/{challenge_id}/attempt", {}),
            ("POST", "/api/v1/docker_challenges", {"challenge_id": challenge_id}),
        ]

        for method, path, body in attempts:
            try:
                resp = await client.request(method, path, json=body, headers=headers)
                if resp.status_code == 403 and not self.token:
                    self._csrf_token = ""
                    headers["CSRF-Token"] = await self._get_csrf()
                    resp = await client.request(method, path, json=body, headers=headers)
                if resp.status_code >= 400:
                    continue
                payload = resp.json()
                conn = self._extract_connection_info(payload)
                if conn:
                    return conn
            except Exception:
                continue

        return ""

    async def _ensure_instance_connection_info(self, challenge: dict[str, Any]) -> str:
        """If challenge supports instances, start one and return fresh connection_info."""
        challenge_id = challenge.get("id")
        if not challenge_id:
            return challenge.get("connection_info") or ""

        # First, check latest challenge detail (connection info may already be present)
        try:
            detail = await self._get(f"/challenges/{challenge_id}")
            latest = detail.get("data", {}) if isinstance(detail, dict) else {}
            conn = self._extract_connection_info(latest)
            if conn:
                challenge["connection_info"] = conn
                return conn
        except Exception:
            pass

        # Try to start an instance if endpoint is supported
        conn = await self._try_start_instance(challenge_id)
        if conn:
            challenge["connection_info"] = conn
            return conn

        # Poll challenge detail briefly in case instance creation is async
        for _ in range(6):
            try:
                await asyncio.sleep(2)
                detail = await self._get(f"/challenges/{challenge_id}")
                latest = detail.get("data", {}) if isinstance(detail, dict) else {}
                conn = self._extract_connection_info(latest)
                if conn:
                    challenge["connection_info"] = conn
                    return conn
            except Exception:
                continue

        return challenge.get("connection_info") or ""

    async def pull_challenge(self, challenge: dict[str, Any], output_dir: str) -> str:
        """Download a challenge's distfiles and write metadata.yml.

        Returns the challenge directory path.
        """
        from pathlib import Path

        import yaml

        name = challenge.get("name", f"challenge-{challenge['id']}")
        # Slugify
        slug = re.sub(r'[<>:"/\\|?*.\x00-\x1f]', "", name.lower().strip())
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"-+", "-", slug).strip("-") or "challenge"

        ch_dir = Path(output_dir) / slug
        ch_dir.mkdir(parents=True, exist_ok=True)

        # If instance-based challenge backend exists, start instance and capture fresh connection info.
        try:
            await self._ensure_instance_connection_info(challenge)
        except Exception as e:
            logger.info("Instance bootstrap skipped for '%s': %s", name, e)

        # Download distfiles using the logged-in session
        await self._ensure_logged_in()
        client = await self._ensure_client()
        for raw_url in challenge.get("files") or []:
            dist_dir = ch_dir / "distfiles"
            dist_dir.mkdir(exist_ok=True)
            base_url_str = (self.base_url or "").rstrip("/")
            url = raw_url if raw_url.startswith("http") else f"{base_url_str}/{raw_url.lstrip('/')}"
            url_path = urlparse(url).path
            # Strip any query params or fragments that may be embedded in the path segment
            raw_fname = url_path.rstrip("/").rsplit("/", 1)[-1] or "file"
            fname = raw_fname.split("?")[0].split("#")[0] or "file"
            dest = dist_dir / fname
            if not dest.exists():
                try:
                    # Only send auth headers to our CTFd server
                    headers = self._base_headers() if self.base_url and urlparse(url).hostname == urlparse(self.base_url).hostname else {}
                    resp = await client.get(
                        url, headers=headers,
                        follow_redirects=True, timeout=60.0,
                    )
                    resp.raise_for_status()

                    # Prefer Content-Disposition filename if provided by the server
                    cd = resp.headers.get("content-disposition", "")
                    cd_match = re.search(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\';\r\n]+)', cd, re.IGNORECASE)
                    if cd_match:
                        cd_fname = cd_match.group(1).strip().strip("\"'")
                        if cd_fname:
                            dest = dist_dir / cd_fname

                    dest.write_bytes(resp.content)
                    logger.info(f"Downloaded: {dest.name} ({len(resp.content)} bytes)")
                except Exception as e:
                    logger.warning(f"Failed to download {url}: {e}")

        # Write metadata.yml
        from markdownify import markdownify as html2md

        desc = challenge.get("description") or ""
        try:
            desc = html2md(desc, heading_style="atx", escape_asterisks=False)
        except Exception:
            pass

        tags = [t["value"] if isinstance(t, dict) else str(t) for t in (challenge.get("tags") or [])]
        meta = {
            "name": name,
            "category": challenge.get("category", ""),
            "description": desc.strip(),
            "value": challenge.get("value", 0),
            "connection_info": challenge.get("connection_info") or "",
            "tags": tags,
            "solves": challenge.get("solves", 0),
        }
        # Add hints
        hints = []
        for h in challenge.get("hints") or []:
            hint = {"cost": h.get("cost", 0)}
            if h.get("content"):
                hint["content"] = h["content"]
            hints.append(hint)
        if hints:
            meta["hints"] = hints

        (ch_dir / "metadata.yml").write_text(
            yaml.dump(meta, allow_unicode=True, default_flow_style=False, sort_keys=False)
        )

        return str(ch_dir)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
