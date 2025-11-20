from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

TerrainBundleType = Literal["dem", "landcover", "roads", "obstacles"]


class TerrainBundleCreate(BaseModel):
    name: str = Field(..., description="Human readable name for the terrain bundle")
    description: str | None = Field(default=None, description="Optional description metadata")
    bundle_path: Path = Field(..., description="Path to the uploaded archive on disk")
    auto_activate: bool = Field(default=True, description="Whether to make this bundle the default")


class TerrainBundleSummary(BaseModel):
    id: str = Field(..., description="Unique identifier for the terrain bundle")
    name: str = Field(..., description="Human readable name for the terrain bundle")
    description: str | None = Field(default=None, description="Optional description metadata")
