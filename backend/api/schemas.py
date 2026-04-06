"""Pydantic schemas for modular API requests/responses."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from backend.run_config import SolverRunConfig


class ConfigResponse(BaseModel):
    run_config: SolverRunConfig
    config_path: str
    settings_summary: dict[str, Any]


class StartRunRequest(BaseModel):
    config: SolverRunConfig | None = None
    persist_config: bool = False


class RunOutputResponse(BaseModel):
    run_id: str
    log_path: str
    content: str


class StartChallengeRequest(BaseModel):
    challenge_id: str = Field(min_length=1)
    launch_solver: bool = True


class SteerChallengeRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    source: str = Field(default="operator", min_length=1, max_length=64)


class CTFSourceSummary(BaseModel):
    id: int
    name: str
    slug: str
    base_url: str
    auth_mode: str
    challenges_root: str
    challenge_count: int
    last_import_at: str | None
    last_import_status: str
    last_import_error: str
    created_at: str
    updated_at: str


class ChallengeCatalogItem(BaseModel):
    id: str
    ctf_id: int
    ctf_name: str
    name: str
    path: str
    category: str
    value: int
    description: str
    connection_info: str
    has_distfiles: bool
    distfile_count: int
    state: str
    run_count: int
    latest_run_id: str | None
    current_run_id: str | None
    latest_flag: str | None
    latest_log_path: str | None
    latest_trace_id: str | None
    steering_log_path: str | None
    started_at: str | None
    finished_at: str | None
    updated_at: str | None


class CTFImportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    ctfd_url: str = Field(min_length=3, max_length=1024)
    auth_mode: Literal["token", "credentials", "none"] = "token"
    token: str = ""
    username: str = ""
    password: str = ""
    challenges_root: str = "challenges"

    @model_validator(mode="after")
    def validate_auth(self) -> CTFImportRequest:
        if self.auth_mode == "none":
            return self
        if self.auth_mode == "token" and not self.token.strip():
            raise ValueError("token is required when auth_mode=token")
        if self.auth_mode == "credentials" and (
            not self.username.strip() or not self.password.strip()
        ):
            raise ValueError(
                "username and password are required when auth_mode=credentials"
            )
        return self


class CTFImportResponse(BaseModel):
    ctf: CTFSourceSummary
    imported_challenges: int
    downloaded_files: int
    root_directory: str
    generated_at: str
