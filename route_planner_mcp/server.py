from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from .data_loader import (
    load_dem,
    load_landcover,
    load_obstacles,
    load_roads,
    obstacle_polygons,
    provenance_status,
)
from .data_models import (
    PaceEstimate,
    RouteCandidate,
    RouteRisk,
    RouteSelectionConstraints,
    RouteSelectionResult,
)
from .exporter import export_all
from .pathfinding import generate_route_candidates
from .pace import estimate_travel_time
from .prompt_templates import NAV_BRIEF_PROMPT
from .risk import evaluate_routes
from .selection import select_route

HANDLING = {"sensitivity": "UNCLASSIFIED", "ttl_hours": 720}
CRS = {"name": "EPSG:4326", "order": "lat,lon"}
SCHEMA = {
    "version": "1.2.0",
    "hash": "sha256:5a0d8a2f96f6c0b8f271f98f6b3a9a8bf5a6a338d250b1d7f4c684a8739d4d5a",
}


def _serialize_datetime(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def route_to_dict(route: RouteCandidate) -> Dict[str, Any]:
    return {
        "id": route.id,
        "distance_m": route.distance_m,
        "ascent_m": route.ascent_m,
        "descent_m": route.descent_m,
        "estimated_cost": route.estimated_cost,
        "composite": route.composite,
        "constraints_used": route.constraints_used,
        "score_breakdown": route.score_breakdown,
        "uncertainty": route.uncertainty,
        "coverage": route.coverage,
        "coverage_units": route.coverage_units,
        "estimated_cost_notes": route.estimated_cost_notes,
        "hydrology_check": route.hydrology_check,
        "mobility": route.mobility,
        "steps": [
            {
                "segment_id": step.segment_id,
                "coordinate": step.coordinate,
                "slope": step.slope,
                "terrain": step.terrain,
                "cost": step.cost,
                "exposure": step.exposure,
                "elevation": step.elevation,
                "type": step.step_type,
                "km_marker": step.km_marker,
                "label": step.label,
            }
            for step in route.steps
        ],
        "provenance": route.provenance,
    }


def risk_to_dict(risk: RouteRisk) -> Dict[str, Any]:
    return {
        "route_id": risk.route_id,
        "slope": risk.slope_risk,
        "exposure": risk.exposure_risk,
        "hydrology": risk.hydrology_risk,
        "weights": risk.weights,
        "formula": risk.formula,
        "components": risk.components,
        "hydrology_check": risk.hydrology_check,
        "aggregate": risk.aggregate,
    }


def pace_to_dict(pace: PaceEstimate) -> Dict[str, Any]:
    return {
        "route_id": pace.route_id,
        "travel_time_minutes": pace.travel_time_minutes,
        "mode": pace.mode,
        "load_kg": pace.load_kg,
        "base_speed_kmh": pace.base_speed_kmh,
        "assumptions": pace.assumptions,
    }


@dataclass
class RoutePlannerState:
    routes: Dict[str, RouteCandidate] = field(default_factory=dict)
    risks: Dict[str, RouteRisk] = field(default_factory=dict)
    paces: Dict[str, PaceEstimate] = field(default_factory=dict)
    selection: Optional[RouteSelectionResult] = None


class RoutePlannerEngine:
    def __init__(self) -> None:
        self.dem = load_dem()
        self.landcover = load_landcover()
        self.obstacles = load_obstacles()
        self.roads = load_roads()
        self.obstacle_polys = obstacle_polygons(self.obstacles)
        self.state = RoutePlannerState()
        self._route_counter = 0

    def nav_route(self, params: Dict[str, Any]) -> Dict[str, Any]:
        start = tuple(params["start"])  # type: ignore[arg-type]
        end = tuple(params["end"])  # type: ignore[arg-type]
        max_candidates = params.get("max_candidates", 3)
        candidates = generate_route_candidates(
            start=start,
            goal=end,
            dem=self.dem,
            landcover=self.landcover,
            obstacle_polys=self.obstacle_polys,
            roads=self.roads,
            max_candidates=max_candidates,
        )
        if not candidates:
            raise ValueError("No viable route found between the provided coordinates.")
        self.state.routes.clear()
        self.state.risks.clear()
        self.state.paces.clear()
        self.state.selection = None
        for candidate in candidates:
            self._route_counter += 1
            candidate.id = f"route-{self._route_counter}"
            self.state.routes[candidate.id] = candidate
            candidate.provenance["sequence_id"] = candidate.id
        return {
            "handling": HANDLING,
            "schema": SCHEMA,
            "crs": CRS,
            "routes": [route_to_dict(route) for route in candidates],
            "provenance": {
                "dem_last_updated": self.dem.metadata.last_updated.isoformat(),
                "landcover_last_updated": self.landcover.metadata.last_updated.isoformat(),
                "ttl_status": [
                    {
                        "dataset": status.dataset,
                        "expired": status.expired,
                        "expires_at": _serialize_datetime(status.expires_at),
                    }
                    for status in provenance_status()
                ],
            },
        }

    def nav_risk_eval(self, params: Dict[str, Any]) -> Dict[str, Any]:
        route_ids = params.get("route_ids")
        if route_ids:
            missing = [rid for rid in route_ids if rid not in self.state.routes]
            if missing:
                raise ValueError(f"Unknown route ids: {', '.join(missing)}")
            routes = [self.state.routes[rid] for rid in route_ids]
        else:
            routes = list(self.state.routes.values())
        risks = evaluate_routes(routes)
        self.state.risks.update(risks)
        for rid, risk in risks.items():
            candidate = self.state.routes.get(rid)
            if candidate:
                candidate.composite = round(candidate.estimated_cost * (1 + risk.aggregate), 3)
        weights_snapshot = risks[next(iter(risks))].weights.copy() if risks else {}
        return {
            "handling": HANDLING,
            "schema": SCHEMA,
            "weights": weights_snapshot,
            "risks": [risk_to_dict(risks[rid]) for rid in risks],
        }

    def nav_pace_estimator(self, params: Dict[str, Any]) -> Dict[str, Any]:
        mode = params.get("mode", "foot")
        load_kg = params.get("load_kg", 25.0)
        route_ids = params.get("route_ids") or list(self.state.routes.keys())
        results = {}
        for route_id in route_ids:
            if route_id not in self.state.routes:
                raise ValueError(f"Unknown route id: {route_id}")
            route = self.state.routes[route_id]
            pace = estimate_travel_time(route, mode, load_kg)
            self.state.paces[route_id] = pace
            results[route_id] = pace
        return {
            "handling": HANDLING,
            "schema": SCHEMA,
            "pace_estimates": [pace_to_dict(p) for p in results.values()],
        }

    def nav_select(self, params: Dict[str, Any]) -> Dict[str, Any]:
        route_ids = params.get("route_ids") or list(self.state.routes.keys())
        missing = [rid for rid in route_ids if rid not in self.state.routes]
        if missing:
            raise ValueError(f"Unknown route ids: {', '.join(missing)}")
        routes = [self.state.routes[rid] for rid in route_ids]
        missing_risk = [rid for rid in route_ids if rid not in self.state.risks]
        missing_pace = [rid for rid in route_ids if rid not in self.state.paces]
        if missing_risk:
            raise ValueError(f"Missing risk evaluation for: {', '.join(missing_risk)}")
        if missing_pace:
            raise ValueError(f"Missing pace estimates for: {', '.join(missing_pace)}")
        risks = {rid: self.state.risks[rid] for rid in route_ids}
        paces = {rid: self.state.paces[rid] for rid in route_ids}

        constraints = RouteSelectionConstraints(
            must_arrive_before=self._parse_datetime(params.get("must_arrive_before")),
            avoid_slope_degrees=params.get("avoid_slope_degrees"),
            prefer_low_risk=params.get("prefer_low_risk", True),
            max_distance_m=params.get("max_distance_m"),
        )
        result = select_route(routes, risks, paces, constraints)
        self.state.selection = result
        return {
            "handling": HANDLING,
            "schema": SCHEMA,
            "selection": {
                "route": route_to_dict(result.selected_route),
                "risk": risk_to_dict(result.risk),
                "pace": pace_to_dict(result.pace),
                "rationale": result.rationale,
                "constraints": result.constraints,
                "alternates": result.alternates,
                "score_definition": result.score_definition,
                "tie_breaker": result.tie_breaker,
                "policy": result.policy,
            }
        }

    def nav_export(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.state.selection:
            raise ValueError("No route has been selected. Run nav.select first.")
        basename = params.get("basename")
        export_payload = export_all(self.state.selection, basename=basename)
        export_payload["handling"] = HANDLING
        export_payload["schema"] = SCHEMA
        return export_payload

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))


mcp = FastMCP("route-planner-mcp")
ENGINE = RoutePlannerEngine()


@mcp.tool()
def nav_route(
    start: List[float],
    end: List[float],
    max_candidates: int = 3,
) -> Dict[str, Any]:
    """Generate 1–3 candidate routes between two coordinates."""
    return ENGINE.nav_route({"start": start, "end": end, "max_candidates": max_candidates})


@mcp.tool()
def nav_risk_eval(route_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Evaluate routes for slope, exposure, and hydrology risk with explicit weighting."""
    return ENGINE.nav_risk_eval({"route_ids": route_ids})


@mcp.tool()
def nav_pace_estimator(
    mode: str = "foot",
    load_kg: float = 25.0,
    route_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Estimate travel time using Naismith's rule with load/mode adjustments."""
    return ENGINE.nav_pace_estimator(
        {"mode": mode, "load_kg": load_kg, "route_ids": route_ids}
    )


@mcp.tool()
def nav_select(
    route_ids: Optional[List[str]] = None,
    must_arrive_before: Optional[str] = None,
    avoid_slope_degrees: Optional[float] = None,
    max_distance_m: Optional[float] = None,
    prefer_low_risk: bool = True,
) -> Dict[str, Any]:
    """Select the best candidate route given commander constraints."""
    return ENGINE.nav_select(
        {
            "route_ids": route_ids,
            "must_arrive_before": must_arrive_before,
            "avoid_slope_degrees": avoid_slope_degrees,
            "max_distance_m": max_distance_m,
            "prefer_low_risk": prefer_low_risk,
        }
    )


@mcp.tool()
def nav_export(basename: Optional[str] = None) -> Dict[str, Any]:
    """Export the selected route to GeoJSON/GPX and generate a Markdown mission brief.

    Args:
        basename: Optional file stem for all exports (defaults to selected route id).
    """
    return ENGINE.nav_export({"basename": basename})


@mcp.prompt(name="@nav/brief")
def nav_brief_prompt() -> str:
    """Mission briefing template for summarizing the selected route."""
    return NAV_BRIEF_PROMPT


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()


