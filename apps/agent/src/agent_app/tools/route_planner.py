from __future__ import annotations

from typing import Any, Dict, Optional

from route_planner_mcp.server import ENGINE

from agent_app.tools.local_terrain import TerrainContext


class RoutePlannerMCPTool:
    """Thin wrapper around the Route Planner MCP engine for LangGraph tool calls."""

    def __init__(self) -> None:
        self.engine = ENGINE

    def generate_routes(
        self,
        terrain: TerrainContext,
        start: tuple[float, float],
        end: tuple[float, float],
        max_candidates: int = 3,
    ) -> Dict[str, Any]:
        import logging
        logger = logging.getLogger("uvicorn")
        
        # Load the terrain data from the uploaded bundle
        terrain_dir = terrain.dem_path.parent
        logger.info(f"🔄 Reloading terrain data from {terrain_dir}...")
        self.engine.reload_terrain(str(terrain_dir))
        logger.info(f"🧭 Running pathfinding algorithm for {max_candidates} route candidates...")
        result = self.engine.nav_route(
            {
                "start": start,
                "end": end,
                "max_candidates": max_candidates,
            }
        )
        logger.info(f"✅ Pathfinding complete")
        return result

    def evaluate_risk(self, route_ids: Optional[list[str]] = None) -> Dict[str, Any]:
        return self.engine.nav_risk_eval({"route_ids": route_ids})

    def estimate_pace(
        self,
        mode: str,
        load_kg: float,
        route_ids: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        return self.engine.nav_pace_estimator(
            {
                "mode": mode,
                "load_kg": load_kg,
                "route_ids": route_ids,
            }
        )

    def select_route(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.engine.nav_select(payload)

    def export(self, basename: Optional[str] = None) -> Dict[str, Any]:
        return self.engine.nav_export({"basename": basename})
