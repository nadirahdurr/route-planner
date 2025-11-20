from __future__ import annotations

import json
from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from agent_app.tools import (
    HumanApprovalTool,
    LocalTerrainTool,
    RoutePlannerMCPTool,
    UserMemoryTool,
)
from agent_app.llm import get_llm
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger


class RoutePlannerGraph:
    """LangGraph-based controller for orchestrating MCP tools."""

    def __init__(self) -> None:
        self.terrain_tool = LocalTerrainTool()
        self.route_tool = RoutePlannerMCPTool()
        self.memory_tool = UserMemoryTool()
        self.approval_tool = HumanApprovalTool()
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(dict)

        def load_terrain(state: Dict[str, Any]) -> Dict[str, Any]:
            terrain_id = state["terrain_id"]
            terrain = self.terrain_tool.load(terrain_id)
            state["terrain"] = terrain
            logger.debug(
                "Loaded terrain bundle",
                terrain_id=terrain_id,
                dem_path=str(terrain.dem_path),
            )
            return state

        def run_route_planner(state: Dict[str, Any]) -> Dict[str, Any]:
            terrain = state["terrain"]
            start = (state["start_lat"], state["start_lon"])
            end = (state["end_lat"], state["end_lon"])
            logger.info(f"🗺️  Starting route planning from {start} to {end}")
            logger.info(f"📊 Loading terrain data from {terrain.terrain_id}...")
            state["route_response"] = self.route_tool.generate_routes(terrain, start, end)
            logger.info(f"✅ Generated {len(state['route_response'].get('routes', []))} route candidates")
            logger.debug(
                "Generated routes",
                start=start,
                end=end,
                route_count=len(state["route_response"].get("routes", [])),
            )
            return state

        def review_routes(state: Dict[str, Any]) -> Dict[str, Any]:
            route_payload = state["route_response"]
            routes = route_payload.get("routes", [])
            summary = []
            for route in routes:
                summary.append(
                    {
                        "id": route["id"],
                        "distance_km": round(route["distance_m"] / 1000, 2),
                        "estimated_cost": route["estimated_cost"],
                        "coverage": route.get("coverage", {}),
                    }
                )

            messages = [
                SystemMessage(
                    content=(
                        "You are a mission planning assistant who explains tradeoffs between "
                        "candidate routes before a human approval step."
                    )
                ),
                HumanMessage(
                    content=(
                        "Commander preference: {preference}, policy: {policy}. Review these routes "
                        "and flag which one you would escalate for approval:\n{summary}"
                    ).format(
                        preference=state.get("preference", "balanced"),
                        policy=state.get("policy", "prefer_low_risk"),
                        summary=json.dumps(summary, indent=2),
                    )
                ),
            ]

            try:
                llm = get_llm()
                response = llm.invoke(messages)
                content = getattr(response, "content", str(response))
            except Exception as exc:  # noqa: BLE001
                content = (
                    "Ollama decision step failed. Verify the Ollama daemon is running and the model "
                    f"is pulled. Error: {exc}"
                )
                logger.error("Ollama invocation failed", error=str(exc))
            else:
                logger.debug("Ollama decision received", excerpt=content[:200])

            state["llm_decision"] = content
            return state

        graph.add_node("load_terrain", load_terrain)
        graph.add_node("route", run_route_planner)
        graph.add_node("review", review_routes)
        graph.add_edge(START, "load_terrain")
        graph.add_edge("load_terrain", "route")
        graph.add_edge("route", "review")
        graph.add_edge("review", END)
        return graph.compile()

    async def arun(self, **kwargs: Any) -> Dict[str, Any]:
        state = dict(kwargs)
        return await self.graph.ainvoke(state)

    def run(self, **kwargs: Any) -> Dict[str, Any]:
        state = dict(kwargs)
        return self.graph.invoke(state)
