from __future__ import annotations

import math
from typing import Dict, List, Tuple

from .data_models import Coordinate, DEMData, LandcoverData, RouteStep


def coordinate_to_grid(
    coord: Coordinate, dem: DEMData
) -> Tuple[int, int]:
    lat, lon = coord
    origin_lat, origin_lon = dem.metadata.origin
    cell = dem.metadata.cell_size_m
    northing = (lat - origin_lat) * 111_320.0  # approximate meters per degree latitude
    easting = (lon - origin_lon) * 85_000.0  # rough average, adequate for small areas
    row = int(round(northing / cell))
    col = int(round(easting / cell))
    return row, col


def grid_to_coordinate(row: int, col: int, dem: DEMData) -> Coordinate:
    origin_lat, origin_lon = dem.metadata.origin
    cell = dem.metadata.cell_size_m
    lat = origin_lat + (row * cell) / 111_320.0
    lon = origin_lon + (col * cell) / 85_000.0
    return (round(lat, 6), round(lon, 6))


def in_bounds(row: int, col: int, dem: DEMData) -> bool:
    return 0 <= row < dem.height and 0 <= col < dem.width


def slope_between(
    dem: DEMData, r1: int, c1: int, r2: int, c2: int
) -> float:
    elev1 = dem.grid[r1][c1]
    elev2 = dem.grid[r2][c2]
    delta_h = elev2 - elev1
    dist_m = dem.metadata.cell_size_m * math.sqrt((r2 - r1) ** 2 + (c2 - c1) ** 2)
    if dist_m == 0:
        return 0.0
    slope = math.degrees(math.atan(abs(delta_h) / dist_m))
    return slope


def local_slope(dem: DEMData, row: int, col: int) -> float:
    neighbors = [
        (row + dr, col + dc)
        for dr in (-1, 0, 1)
        for dc in (-1, 0, 1)
        if not (dr == 0 and dc == 0)
    ]
    slopes: List[float] = []
    for nr, nc in neighbors:
        if in_bounds(nr, nc, dem):
            slopes.append(slope_between(dem, row, col, nr, nc))
    return max(slopes) if slopes else 0.0


def terrain_cost(
    landcover: LandcoverData, row: int, col: int
) -> float:
    cover = landcover.grid[row][col]
    return landcover.classes[cover].cost_factor


def exposure_score(
    landcover: LandcoverData, row: int, col: int
) -> float:
    cover = landcover.grid[row][col]
    return landcover.classes[cover].exposure


def assemble_route_steps(
    path: List[Tuple[int, int]],
    dem: DEMData,
    landcover: LandcoverData,
    checkpoint_interval_m: float = 250.0,
) -> List[RouteStep]:
    steps: List[RouteStep] = []
    if not path:
        return steps

    cumulative_m = 0.0
    last_checkpoint_m = 0.0
    prev_row, prev_col = path[0]
    last_terrain = landcover.grid[prev_row][prev_col]
    cell = dem.metadata.cell_size_m
    checkpoint_counter = 0

    for segment_id, (row, col) in enumerate(path, start=1):
        if segment_id > 1:
            seg_dist = cell * math.sqrt((row - prev_row) ** 2 + (col - prev_col) ** 2)
            cumulative_m += seg_dist
            prev_row, prev_col = row, col
        coord = grid_to_coordinate(row, col, dem)
        slope = round(local_slope(dem, row, col), 2)
        terrain = landcover.grid[row][col]
        cost = terrain_cost(landcover, row, col)
        exposure = exposure_score(landcover, row, col)
        km_marker = round(cumulative_m / 1000.0, 3)
        base_step = RouteStep(
            segment_id=segment_id,
            coordinate=coord,
            slope=slope,
            terrain=terrain,
            cost=cost,
            exposure=exposure,
            elevation=dem.grid[row][col],
            step_type="segment",
            km_marker=km_marker,
            label=None,
        )
        steps.append(base_step)

        should_checkpoint = False
        if terrain != last_terrain and segment_id > 1:
            should_checkpoint = True
        elif cumulative_m - last_checkpoint_m >= checkpoint_interval_m and segment_id > 1:
            should_checkpoint = True

        if should_checkpoint:
            checkpoint_counter += 1
            if terrain != last_terrain:
                reason = f"Terrain {last_terrain}→{terrain}"
            else:
                reason = f"Distance {int(cumulative_m)} m"
            label = f"CP{checkpoint_counter}: {reason}"
            checkpoint_step = RouteStep(
                segment_id=segment_id,
                coordinate=coord,
                slope=slope,
                terrain=terrain,
                cost=cost,
                exposure=exposure,
                elevation=dem.grid[row][col],
                step_type="checkpoint",
                km_marker=km_marker,
                label=label,
            )
            steps.append(checkpoint_step)
            last_checkpoint_m = cumulative_m
        last_terrain = terrain

    return steps


def route_distance_and_elevation(
    path: List[Tuple[int, int]], dem: DEMData
) -> Tuple[float, float, float]:
    if len(path) < 2:
        return (0.0, 0.0, 0.0)
    dist = 0.0
    ascent = 0.0
    descent = 0.0
    cell = dem.metadata.cell_size_m
    for (r1, c1), (r2, c2) in zip(path[:-1], path[1:]):
        elev1 = dem.grid[r1][c1]
        elev2 = dem.grid[r2][c2]
        segment = cell * math.sqrt((r2 - r1) ** 2 + (c2 - c1) ** 2)
        dist += segment
        if elev2 > elev1:
            ascent += elev2 - elev1
        else:
            descent += elev1 - elev2
    return (dist, ascent, descent)


