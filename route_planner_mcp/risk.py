from __future__ import annotations

from statistics import mean
from typing import Dict, Iterable

from .data_models import RouteCandidate, RouteRisk

RISK_WEIGHTS = {"slope": 0.45, "exposure": 0.35, "hydrology": 0.2}
RISK_FORMULA = "sum(w[i] * component[i])"


def _normalized(value: float, upper: float) -> float:
    if upper == 0:
        return 0.0
    return max(0.0, min(1.0, value / upper))


def slope_risk(steps) -> float:
    segment_steps = [step for step in steps if step.step_type == "segment"]
    if not segment_steps:
        return 0.0
    worst = max(step.slope for step in segment_steps)
    avg = mean(step.slope for step in segment_steps)
    score = 0.6 * _normalized(avg, 15.0) + 0.4 * _normalized(worst, 25.0)
    return round(min(score, 1.0), 3)


def exposure_risk(steps) -> float:
    segment_steps = [step for step in steps if step.step_type == "segment"]
    if not segment_steps:
        return 0.0
    avg_exposure = mean(step.exposure for step in segment_steps)
    return round(_normalized(avg_exposure, 1.0), 3)


def hydrology_risk(steps) -> float:
    segment_steps = [step for step in steps if step.step_type == "segment"]
    if not segment_steps:
        return 0.0
    water_penalty = sum(1 for step in segment_steps if "water" in step.terrain.lower())
    bog_penalty = sum(1 for step in segment_steps if "wetland" in step.terrain.lower())
    total = len(segment_steps)
    score = _normalized(water_penalty * 2 + bog_penalty, max(total, 1))
    return round(score, 3)


def evaluate_routes(
    routes: Iterable[RouteCandidate],
) -> Dict[str, RouteRisk]:
    risk_map: Dict[str, RouteRisk] = {}
    for route in routes:
        slope_component = slope_risk(route.steps)
        exposure_component = exposure_risk(route.steps)
        hydrology_component = hydrology_risk(route.steps)
        risk = RouteRisk(
            route_id=route.id,
            slope_risk=slope_component,
            exposure_risk=exposure_component,
            hydrology_risk=hydrology_component,
            weights=RISK_WEIGHTS.copy(),
            formula=RISK_FORMULA,
            components={
                "slope": slope_component,
                "exposure": exposure_component,
                "hydrology": hydrology_component,
            },
            hydrology_check=route.hydrology_check,
        )
        risk_map[route.id] = risk
    return risk_map


