from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RunType(StrEnum):
    FULL_REPORT = "full_report"


class RunStatus(StrEnum):
    INIT = "INIT"
    INGESTING = "INGESTING"
    ANALYZING = "ANALYZING"
    VALUATING = "VALUATING"
    SYNTHESIZING = "SYNTHESIZING"
    AUDITING = "AUDITING"
    PUBLISHED = "PUBLISHED"
    PUBLISHED_DRAFT = "PUBLISHED_DRAFT"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class StartRunRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    run_type: RunType = RunType.FULL_REPORT
    objective: str = Field(default="Generate grounded equity research output for selected ticker.")
    scenarios: list[str] = Field(default_factory=lambda: ["base", "bull", "bear"])
    org_id: str | None = None
    requested_by: str | None = None
    budget_policy: str | None = None


class StartRunResponse(BaseModel):
    run_id: str
    status: RunStatus


class GenerateReportResponse(BaseModel):
    run_id: str
    # "fast_render" (render from existing artifacts) or "full_pipeline".
    mode: str


class RunStatusResponse(BaseModel):
    run_id: str
    ticker: str
    run_type: RunType
    status: RunStatus
    current_stage: str
    # Fine-grained within-stage detail for the live progress modal, e.g.
    # {"substep": "cafef", "detail": "Đang tìm trên CafeF…"}.
    progress: dict[str, Any] = Field(default_factory=dict)
    # Human-readable reason a run cannot produce a report (Vietnamese-friendly).
    blocking_reason: str | None = None
    flags: dict[str, Any]
    created_at: str
    updated_at: str
    finished_at: str | None = None


class ArtifactItem(BaseModel):
    artifact_id: str
    artifact_type: str
    section_key: str | None = None
    payload: dict[str, Any]
    confidence: float | None = None
    created_by_agent: str | None = None
    created_at: str


class ArtifactsResponse(BaseModel):
    run_id: str
    artifacts: list[ArtifactItem]


class RecomputeRequest(BaseModel):
    event_type: str
    reason: str = ""

