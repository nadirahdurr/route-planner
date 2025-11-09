from __future__ import annotations

import heapq
import math
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

from shapely.geometry import Point, Polygon

from .data_models import RouteCandidate
from .terrain import (
    assemble_route_steps,
    coordinate_to_grid,
    in_bounds,
    route_distance_and_elevation,
    slope_between,
    terrain_cost,
    exposure_score,
    grid_to_coordinate,
)

Coordinate = Tuple[float, float]
GridIndex = Tuple[int, int]


def _cell_centroid(row: int, col: int, origin: Coordinate, cell_size: float) -> Point:
    lat = origin[0] + ((row + 0.5) * cell_size) / 111_320.0
    lon = origin[1] + ((col + 0.5) * cell_size) / 85_000.0
    return Point(lon, lat)


def _is_blocked(
    row: int,
    col: int,
    obstacle_index: Optional[STRtree],
) -> bool:
    if obstacle_index is None:
        return False
    centroid = _cell_centroid(
        row,
        col,
        obstacle_index.geometries[0].bounds[:2],  # placeholder, overwritten later
        1.0,
    )
    return any(poly.contains(centroid) for poly in obstacle_index.geometries)


def _approx_distance(coord1: Coordinate, coord2: Coordinate) -> float:
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    dlat = (lat2 - lat1) * 111_320.0
    dlon = (lon2 - lon1) * 85_000.0
    return math.sqrt(dlat**2 + dlon**2)


def _road_influence(
    roads: Dict[str, List[Coordinate]],
    coord: Coordinate,
) -> float:
    if not roads:
        return 1.0
    best_distance = min(
        _approx_distance(coord, road_coord) for road in roads.values() for road_coord in road
    )
    if best_distance < 100:  # meters
        return 0.7
    if best_distance < 300:
        return 0.85
    if best_distance < 500:
        return 0.95
    return 1.0


def heuristic(a: GridIndex, b: GridIndex, cell_size: float) -> float:
    return cell_size * math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def a_star_route(
    start: Coordinate,
    goal: Coordinate,
    dem,
    landcover,
    obstacle_polys: Iterable[Polygon],
    roads: Dict[str, List[Coordinate]],
    slope_weight: float = 1.0,
    terrain_multipliers: Optional[Dict[str, float]] = None,
    exposure_penalty: float = 0.0,
    road_bias: float = 1.0,
) -> Optional[List[GridIndex]]:
    start_idx = coordinate_to_grid(start, dem)
    goal_idx = coordinate_to_grid(goal, dem)
    if not in_bounds(*start_idx, dem) or not in_bounds(*goal_idx, dem):
        return None

    obstacle_list = list(obstacle_polys)
    cell_size = dem.metadata.cell_size_m
    origin = dem.metadata.origin

    def cell_blocked(row: int, col: int) -> bool:
        if not obstacle_list:
            return False
        centroid = _cell_centroid(row, col, origin, cell_size)
        for poly in obstacle_list:
            if poly.contains(centroid):
                return True
        return False

    open_set: List[Tuple[float, GridIndex]] = []
    heapq.heappush(open_set, (0, start_idx))

    came_from: Dict[GridIndex, GridIndex] = {}
    g_score: Dict[GridIndex, float] = {start_idx: 0.0}
    f_score: Dict[GridIndex, float] = {start_idx: heuristic(start_idx, goal_idx, cell_size)}

    neighbors = [
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    ]

    while open_set:
        _, current = heapq.heappop(open_set)
        if current == goal_idx:
            path: List[GridIndex] = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            return list(reversed(path))

        for dr, dc in neighbors:
            nr, nc = current[0] + dr, current[1] + dc
            if not in_bounds(nr, nc, dem):
                continue
            if cell_blocked(nr, nc):
                continue

            terrain_name = landcover.grid[nr][nc]
            terrain_factor = terrain_cost(landcover, nr, nc)
            if terrain_multipliers:
                terrain_factor *= terrain_multipliers.get(terrain_name, 1.0)
            slope = slope_between(dem, current[0], current[1], nr, nc)
            slope_factor = 1.0 + (slope / 30.0) * slope_weight

            coord = grid_to_coordinate(nr, nc, dem)
            road_factor = _road_influence(roads, coord)
            if road_bias != 1.0:
                road_factor = math.pow(road_factor, road_bias)

            exposure_factor = 1.0 + exposure_penalty * exposure_score(landcover, nr, nc)

            move_cost = cell_size * math.sqrt(dr**2 + dc**2)
            tentative_g = (
                g_score[current]
                + move_cost * terrain_factor * slope_factor * road_factor * exposure_factor
            )

            neighbor = (nr, nc)
            if tentative_g < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f_score[neighbor] = tentative_g + heuristic(neighbor, goal_idx, cell_size)
                heapq.heappush(open_set, (f_score[neighbor], neighbor))

    return None


def generate_route_candidates(
    start: Coordinate,
    goal: Coordinate,
    dem,
    landcover,
    obstacle_polys: Iterable[Polygon],
    roads: Dict[str, List[Coordinate]],
    max_candidates: int = 3,
) -> List[RouteCandidate]:
    profiles = [
        {
            "id": "balanced",
            "label": "Balanced surfaces",
            "slope_weight": 1.0,
            "terrain_multipliers": {"trail": 0.75, "road": 0.8},
            "exposure_penalty": 0.05,
            "road_bias": 1.0,
            "constraints": {"avoid": [], "prefer": ["mixed"], "mode": "foot"},
            "cost_weights": {"slope": 0.4, "terrain": 0.35, "exposure": 0.25},
        },
        {
            "id": "trail_pref",
            "label": "Prefer trails",
            "slope_weight": 0.9,
            "terrain_multipliers": {"trail": 0.6, "road": 0.85, "forest": 1.1, "open": 1.2},
            "exposure_penalty": 0.03,
            "road_bias": 0.8,
            "constraints": {"avoid": [], "prefer": ["trail"], "mode": "foot"},
            "cost_weights": {"slope": 0.35, "terrain": 0.45, "exposure": 0.2},
        },
        {
            "id": "low_exposure",
            "label": "Limit exposure",
            "slope_weight": 1.2,
            "terrain_multipliers": {"open": 1.4, "trail": 0.85, "road": 0.8},
            "exposure_penalty": 0.12,
            "road_bias": 1.1,
            "constraints": {"avoid": ["open"], "prefer": ["cover"], "mode": "foot"},
            "cost_weights": {"slope": 0.45, "terrain": 0.25, "exposure": 0.3},
        },
    ][:max_candidates]
    candidates: List[RouteCandidate] = []

    for idx, profile in enumerate(profiles, start=1):
        path = a_star_route(
            start,
            goal,
            dem,
            landcover,
            obstacle_polys,
            roads,
            slope_weight=profile["slope_weight"],
            terrain_multipliers=profile["terrain_multipliers"],
            exposure_penalty=profile["exposure_penalty"],
            road_bias=profile["road_bias"],
        )
        if not path:
            continue
        steps = assemble_route_steps(path, dem, landcover)
        segment_steps = [step for step in steps if step.step_type == "segment"]
        distance, ascent, descent = route_distance_and_elevation(path, dem)
        if not segment_steps:
            continue

        terrain_adjusted = [
            step.cost * profile["terrain_multipliers"].get(step.terrain, 1.0) for step in segment_steps
        ]
        avg_slope = sum(step.slope for step in segment_steps) / len(segment_steps)
        avg_terrain = sum(terrain_adjusted) / len(terrain_adjusted)
        avg_exposure = sum(step.exposure for step in segment_steps) / len(segment_steps)

        weights = profile["cost_weights"]
        score_breakdown = {
            "slope": round(avg_slope, 3),
            "terrain": round(avg_terrain, 3),
            "exposure": round(avg_exposure, 3),
        }
        estimated_cost = round(
            weights["slope"] * score_breakdown["slope"]
            + weights["terrain"] * score_breakdown["terrain"]
            + weights["exposure"] * score_breakdown["exposure"],
            3,
        )

        terrain_distance: Dict[str, float] = defaultdict(float)
        hydrology_terms = ("wetland", "water")
        hydrology_crossings = 0
        nearest_hydro_m: Optional[float] = None
        segment_steps = [step for step in steps if step.step_type == "segment"]
        cell_size = dem.metadata.cell_size_m

        prev_is_hydro = False
        for idx in range(1, len(path)):
            (r1, c1), (r2, c2) = path[idx - 1], path[idx]
            terrain_name = landcover.grid[r2][c2]
            seg_dist = cell_size * math.sqrt((r2 - r1) ** 2 + (c2 - c1) ** 2)
            terrain_distance[terrain_name] += seg_dist
            step = segment_steps[idx]
            is_hydro = any(term in terrain_name.lower() for term in hydrology_terms)
            if is_hydro and not prev_is_hydro:
                hydrology_crossings += 1
            if is_hydro:
                distance_m = step.km_marker * 1000.0
                if nearest_hydro_m is None or distance_m < nearest_hydro_m:
                    nearest_hydro_m = distance_m
            prev_is_hydro = is_hydro

        coverage_km = {name: round(dist / 1000.0, 3) for name, dist in terrain_distance.items()}
        total_km = sum(coverage_km.values()) or 1.0
        mobility = {
            "surface_mix": {
                f"{name}_pct": round((dist / total_km) * 100, 1) for name, dist in coverage_km.items()
            },
            "avg_slope_deg": round(sum(step.slope for step in segment_steps) / len(segment_steps), 2),
            "max_slope_deg": round(max(step.slope for step in segment_steps), 2),
        }
        hydrology_check = {
            "crossings": hydrology_crossings,
            "nearest_water_m": round(nearest_hydro_m, 1) if nearest_hydro_m is not None else None,
        }

        candidate = RouteCandidate(
            id=f"route-{idx}",
            steps=steps,
            distance_m=round(distance, 1),
            ascent_m=round(ascent, 1),
            descent_m=round(descent, 1),
            estimated_cost=estimated_cost,
            composite=None,
            constraints_used=profile["constraints"],
            score_breakdown=score_breakdown,
            uncertainty={
                "dem_res_m": dem.metadata.cell_size_m,
                "est_slope_error_deg": 0.5,
                "landcover_update_ts": landcover.metadata.last_updated.isoformat(),
            },
            coverage=coverage_km,
            coverage_units="km",
            estimated_cost_notes=(
                "dimensionless composite: weighted sum of average slope, terrain cost, exposure"
            ),
            hydrology_check=hydrology_check,
            mobility=mobility,
            provenance={
                "profile": profile["id"],
                "profile_label": profile["label"],
                "cost_weights": weights,
                "slope_weight": profile["slope_weight"],
                "terrain_multipliers": profile["terrain_multipliers"],
                "exposure_penalty": profile["exposure_penalty"],
                "road_bias": profile["road_bias"],
                "dem_last_updated": dem.metadata.last_updated.isoformat(),
                "landcover_last_updated": landcover.metadata.last_updated.isoformat(),
            },
        )
        candidates.append(candidate)

    return candidates


