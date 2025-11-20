from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional, List

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    debug: bool = Field(default=False, description="Enable FastAPI debug mode")
    data_root: Path = Field(
        default=Path("var/data"),
        description="Base directory for uploaded terrain bundles",
    )
    export_root: Path = Field(
        default=Path("var/exports"),
        description="Base directory for agent export artifacts",
    )
    database_url: str = Field(
        default="sqlite+aiosqlite:///var/data/agent.db",
        description="SQLModel connection string",
    )
    route_planner_package: Optional[Path] = Field(
        default=Path("../../packages/route_planner_mcp"),
        description="Optional path to the local route planner package for dynamic imports",
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama server base URL",
    )
    ollama_model: str = Field(
        default="llama3.1:8b",
        description="Ollama model identifier used for decision making",
    )
    cors_allow_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Comma separated list of origins allowed for CORS",
    )

    class Config:
        env_prefix = "ROUTE_AGENT_"
        env_file = ".env"
        case_sensitive = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.data_root.mkdir(parents=True, exist_ok=True)
    settings.export_root.mkdir(parents=True, exist_ok=True)
    return settings
