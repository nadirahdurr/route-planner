from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

RoutePreference = Literal["balanced", "trail_pref", "low_exposure"]
SelectionPolicy = Literal["prefer_low_risk", "cost_only"]


class PlanCreateRequest(BaseModel):
    terrain_id: str = Field(..., description="Identifier of the terrain bundle to use")
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    preference: RoutePreference = Field(default="balanced")
    policy: SelectionPolicy = Field(default="prefer_low_risk")
    load_kg: float = Field(default=20.0, ge=0)
    mode: Literal["foot", "wheeled"] = Field(default="foot")
    notes: Optional[str] = Field(default=None, description="Operator notes attached to the run")


class PlanRunStatus(BaseModel):
    run_id: str
    status: Literal["queued", "running", "awaiting_approval", "completed", "failed"]
    created_at: datetime
    updated_at: datetime
    message: Optional[str] = None


class PlanResult(BaseModel):
    run_id: str
    approved_route_id: Optional[str]
    artifact_base: Optional[str]
    export_paths: list[str] = Field(default_factory=list)
    completed_at: Optional[datetime] = None
    llm_brief: Optional[str] = None
    route_payload: Optional[Dict[str, Any]] = None
