from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional

from .data_models import (
    PaceEstimate,
    RouteCandidate,
    RouteRisk,
    RouteSelectionConstraints,
    RouteSelectionResult,
)


def select_route(
    routes: Iterable[RouteCandidate],
    risks: Dict[str, RouteRisk],
    paces: Dict[str, PaceEstimate],
    constraints: Optional[RouteSelectionConstraints] = None,
) -> RouteSelectionResult:
    constraints = constraints or RouteSelectionConstraints()
    best_choice: Optional[RouteCandidate] = None
    best_score = float("inf")
    rationale_parts = []
    evaluations = []

    for route in routes:
        risk = risks[route.id]
        pace = paces[route.id]

        if constraints.avoid_slope_degrees is not None:
            if max(step.slope for step in route.steps) > constraints.avoid_slope_degrees:
                rationale_parts.append(f"{route.id} rejected: slope above threshold")
                continue

        if constraints.max_distance_m is not None and route.distance_m > constraints.max_distance_m:
            rationale_parts.append(f"{route.id} rejected: distance exceeds limit")
            continue

        if constraints.must_arrive_before is not None:
            now = datetime.now(timezone.utc)
            arrival = now + timedelta(minutes=pace.travel_time_minutes)
            if arrival > constraints.must_arrive_before:
                rationale_parts.append(f"{route.id} rejected: ETA past deadline")
                continue

        score = route.estimated_cost
        if constraints.prefer_low_risk:
            score *= (1 + risks[route.id].aggregate)

        if score < best_score:
            best_score = score
            best_choice = route

        evaluations.append(
            {
                "route": route,
                "score": score,
                "risk": risk,
                "pace": pace,
                "rejected": score == float("inf"),
            }
        )

    if best_choice is None:
        raise ValueError("No route satisfies the provided constraints.")

    risk = risks[best_choice.id]
    pace = paces[best_choice.id]
    rationale_parts.append(f"{best_choice.id} selected with aggregate risk {risk.aggregate:.2f}")
    rationale = "; ".join(rationale_parts)

    constraints_summary = {
        "nlt": constraints.must_arrive_before.isoformat() if constraints.must_arrive_before else None,
        "max_slope_deg": constraints.avoid_slope_degrees,
        "max_distance_m": constraints.max_distance_m,
        "preferred": "lowest_risk" if constraints.prefer_low_risk else "balanced",
    }
    constraints_summary = {k: v for k, v in constraints_summary.items() if v is not None}

    alternates: List[Dict[str, Any]] = []
    best_distance = best_choice.distance_m
    best_risk = risk
    best_score = next(ev["score"] for ev in evaluations if ev["route"].id == best_choice.id)
    best_cost = best_choice.estimated_cost
    best_composite = best_choice.composite if best_choice.composite is not None else round(best_score, 3)
    for evaluation in evaluations:
        route = evaluation["route"]
        if route.id == best_choice.id:
            continue
        alt_risk = evaluation["risk"]
        alt_pace = evaluation["pace"]
        alt_score = evaluation["score"]
        alt_cost = route.estimated_cost
        reason_parts = []
        reason_codes: List[str] = []
        risk_diff = alt_risk.aggregate - best_risk.aggregate
        if abs(risk_diff) < 0.01:
            reason_parts.append("similar aggregate risk")
            reason_codes.append("tie_risk")
        elif risk_diff > 0:
            reason_parts.append(f"higher aggregate risk (+{risk_diff:.2f})")
            reason_codes.append("higher_risk")
        else:
            reason_parts.append(f"lower aggregate risk ({alt_risk.aggregate:.2f} vs {best_risk.aggregate:.2f})")
            reason_codes.append("lower_risk")
        if alt_pace.travel_time_minutes > pace.travel_time_minutes:
            reason_parts.append(
                f"slower ETA (+{alt_pace.travel_time_minutes - pace.travel_time_minutes:.1f} min)"
            )
            reason_codes.append("slower_eta")
        elif alt_pace.travel_time_minutes < pace.travel_time_minutes:
            reason_parts.append(
                f"faster ETA (-{pace.travel_time_minutes - alt_pace.travel_time_minutes:.1f} min)"
            )
            reason_codes.append("faster_eta")
        if route.distance_m > best_distance:
            reason_parts.append("longer distance")
            reason_codes.append("longer_distance")
        elif route.distance_m < best_distance:
            reason_parts.append("shorter distance")
            reason_codes.append("shorter_distance")
        if route.constraints_used.get("prefer"):
            reason_parts.append(f"prefers {', '.join(route.constraints_used['prefer'])}")
            for pref in route.constraints_used["prefer"]:
                if pref == "trail":
                    reason_codes.append("trail_pref")
                elif pref == "mixed":
                    reason_codes.append("mixed_profile")
                elif pref == "cover":
                    reason_codes.append("cover_pref")
        if route.coverage:
            dominant = max(route.coverage.items(), key=lambda item: item[1])[0]
            reason_parts.append(f"dominant terrain {dominant}")
            reason_codes.append(f"dominant_{dominant}")
        if route.constraints_used.get("avoid") and route.coverage:
            if "open" in route.constraints_used["avoid"] and route.coverage.get("open", 0.0) > 0:
                reason_codes.append("requires_open_crossing")
        if alt_cost > best_cost:
            reason_codes.append("higher_cost")
        elif alt_cost < best_cost:
            reason_codes.append("lower_cost")
        alternates.append(
            {
                "route_id": route.id,
                "score": round(alt_score, 3),
                "rationale": ", ".join(reason_parts),
                "reason_codes": sorted(set(reason_codes)),
            }
        )

    alternates.sort(key=lambda item: item["score"])

    sorted_evals = sorted(evaluations, key=lambda item: item["score"])
    tie_breaker = "lowest composite score"
    if len(sorted_evals) > 1:
        runner = sorted_evals[1]
        tie_breaker = (
            f"lowest composite score ({best_composite:.3f} vs {runner['score']:.3f}) "
            f"and lower estimated_cost ({best_cost:.3f} vs {runner['route'].estimated_cost:.3f})"
        )
        if best_choice.coverage:
            dominant = max(best_choice.coverage.items(), key=lambda item: item[1])[0]
            tie_breaker += f"; selected profile emphasizes {dominant}"

    score_definition = (
        "composite score = estimated_cost × (1 + aggregate_risk) when prefer_low_risk "
        "else estimated_cost"
    )

    policy = {
        "id": "prefer_low_risk_v1.1" if constraints.prefer_low_risk else "balanced_v1.1",
        "composite": "estimated_cost * (1 + aggregate_risk)" if constraints.prefer_low_risk else "estimated_cost",
        "tiebreakers": [
            "lowest composite",
            "lowest estimated_cost",
            "greater trail_km",
        ],
    }

    return RouteSelectionResult(
        selected_route=best_choice,
        risk=risk,
        pace=pace,
        rationale=rationale,
        constraints=constraints_summary,
        alternates=alternates,
        score_definition=score_definition,
        tie_breaker=tie_breaker,
        policy=policy,
    )


