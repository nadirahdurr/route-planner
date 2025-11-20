from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any, Dict

from .server import RoutePlannerEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Route Planner MCP CLI")
    parser.add_argument("--start", nargs=2, type=float, required=True, metavar=("LAT", "LON"))
    parser.add_argument("--end", nargs=2, type=float, required=True, metavar=("LAT", "LON"))
    parser.add_argument("--mode", choices=["foot", "wheeled"], default="foot")
    parser.add_argument("--load-kg", type=float, default=25.0)
    parser.add_argument("--max-candidates", type=int, default=3)
    parser.add_argument("--must-arrive-before", type=str, default=None)
    parser.add_argument("--avoid-slope", type=float, default=None)
    parser.add_argument("--max-distance", type=float, default=None)
    parser.add_argument("--export-name", type=str, default=None, help="Basename for exported files.")
    parser.add_argument("--prefer-low-risk", action="store_true", default=True)
    parser.add_argument(
        "--no-prefer-low-risk",
        dest="prefer_low_risk",
        action="store_false",
        help="Disable preference for lowest aggregate risk.",
    )
    return parser.parse_args()


def run_pipeline(args: argparse.Namespace) -> Dict[str, Any]:
    engine = RoutePlannerEngine()

    route_result = engine.nav_route(
        {
            "start": args.start,
            "end": args.end,
            "max_candidates": args.max_candidates,
        }
    )

    route_ids = [route["id"] for route in route_result["routes"]]

    risk_result = engine.nav_risk_eval({"route_ids": route_ids})

    pace_result = engine.nav_pace_estimator(
        {"route_ids": route_ids, "mode": args.mode, "load_kg": args.load_kg}
    )

    selection_params = {
        "route_ids": route_ids,
        "must_arrive_before": args.must_arrive_before,
        "avoid_slope_degrees": args.avoid_slope,
        "max_distance_m": args.max_distance,
        "prefer_low_risk": args.prefer_low_risk,
    }
    selection_result = engine.nav_select(selection_params)

    export_params = {"basename": args.export_name} if args.export_name else {}
    export_result = engine.nav_export(export_params)

    for route_entry in route_result["routes"]:
        candidate = engine.state.routes.get(route_entry["id"])
        if candidate and candidate.composite is not None:
            route_entry["composite"] = candidate.composite

    return {
        "routes": route_result,
        "risks": risk_result,
        "pace": pace_result,
        "selection": selection_result,
        "exports": export_result,
    }


def main() -> None:
    args = parse_args()
    results = run_pipeline(args)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()


