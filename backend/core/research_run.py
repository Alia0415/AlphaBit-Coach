"""Observable state contract for research planning runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ResearchRunStage = Literal[
    "received",
    "interpreting",
    "interpreted",
    "selecting_agents",
    "agents_selected",
    "building_dag",
    "validating_dag",
    "plan_ready",
    "executing",
    "failed",
]
ResearchRunStatus = Literal["running", "plan_ready", "executing", "failed"]
ResearchWorkflowMode = Literal["dynamic", "stock_analysis"]


STAGE_PROGRESS: dict[ResearchRunStage, int] = {
    "received": 2,
    "interpreting": 12,
    "interpreted": 25,
    "selecting_agents": 38,
    "agents_selected": 58,
    "building_dag": 70,
    "validating_dag": 86,
    "plan_ready": 100,
    "executing": 100,
    "failed": 0,
}


class ResearchRunState(BaseModel):
    """The persisted, backend-owned truth for one planning run."""

    run_id: str
    workflow_mode: ResearchWorkflowMode = "dynamic"
    status: ResearchRunStatus
    current_stage: ResearchRunStage
    progress: int = Field(ge=0, le=100)
    started_at: datetime
    selected_agents: list[dict[str, Any]] = Field(default_factory=list)
    dag: dict[str, Any] | None = None
    elapsed_ms: int = Field(ge=0)
    estimated_remaining_ms: int | None = Field(default=None, ge=0)
    error: str | None = None
    failed_stage: ResearchRunStage | None = None
    message: str


class ResearchRunCreated(BaseModel):
    run_id: str
    status: Literal["running"] = "running"
    events_url: str
    status_url: str
