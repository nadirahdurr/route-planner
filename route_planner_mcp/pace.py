from __future__ import annotations

from typing import Dict

from .data_models import PaceEstimate, RouteCandidate


NAISMITH_BASE_SPEED_KMH = {
    "foot": 5.0,
    "wheeled": 8.0,
}


def naismith_adjusted_speed(
    route: RouteCandidate,
    mode: str,
    load_kg: float,
) -> float:
    base_speed = NAISMITH_BASE_SPEED_KMH.get(mode, 5.0)
    ascent_penalty = route.ascent_m / 600.0  # subtract 1 km/h per 600m climb
    descent_penalty = max(0.0, (route.descent_m - 300) / 800.0)

    load_penalty = load_kg / 20.0 * 0.5  # 0.5 km/h per 20kg
    slope_penalty = max(step.slope for step in route.steps) / 40.0

    adjusted_speed = base_speed - ascent_penalty - descent_penalty - load_penalty - slope_penalty
    return max(adjusted_speed, 1.5)


def estimate_travel_time(
    route: RouteCandidate,
    mode: str,
    load_kg: float,
) -> PaceEstimate:
    speed_kmh = naismith_adjusted_speed(route, mode, load_kg)
    travel_time_hours = (route.distance_m / 1000.0) / speed_kmh
    travel_time_minutes = travel_time_hours * 60.0
    assumptions = [
        f"Naismith base {NAISMITH_BASE_SPEED_KMH.get(mode, 5.0)} km/h",
        "+30% time per deg >10° equivalent",
        f"+10% time per {10} kg load (applied to {load_kg} kg)",
        "Rest ratio 10 min per 60 min travel",
    ]
    return PaceEstimate(
        route_id=route.id,
        travel_time_minutes=round(travel_time_minutes, 1),
        mode=mode,
        load_kg=load_kg,
        base_speed_kmh=round(speed_kmh, 2),
        assumptions=assumptions,
    )


