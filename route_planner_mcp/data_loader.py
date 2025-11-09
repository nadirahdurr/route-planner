from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from shapely.geometry import Polygon

from .data_models import (
    Coordinate,
    DEMData,
    GridMetadata,
    LandcoverClass,
    LandcoverData,
    Obstacle,
    ProvenanceStatus,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _load_grid_metadata(raw: Dict) -> GridMetadata:
    meta = raw["metadata"]
    return GridMetadata(
        origin=(meta["origin"]["lat"], meta["origin"]["lon"]),
        cell_size_m=meta["cell_size_m"],
        ttl_hours=meta["ttl_hours"],
        last_updated=_parse_timestamp(meta["last_updated"]),
    )


def load_dem(path: Path | None = None) -> DEMData:
    source = path or DATA_DIR / "dem.json"
    with source.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    metadata = _load_grid_metadata(payload)
    grid = payload["grid"]
    return DEMData(grid=grid, metadata=metadata)


def load_landcover(path: Path | None = None) -> LandcoverData:
    source = path or DATA_DIR / "landcover.json"
    with source.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    metadata = _load_grid_metadata(payload)
    classes = {
        name: LandcoverClass(
            name=name,
            cost_factor=value["cost_factor"],
            exposure=value["exposure"],
            speed_modifier=value["speed_modifier"],
        )
        for name, value in payload["classes"].items()
    }
    return LandcoverData(grid=payload["grid"], classes=classes, metadata=metadata)


def load_obstacles(path: Path | None = None) -> List[Obstacle]:
    source = path or DATA_DIR / "obstacles.geojson"
    with source.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    obstacles: List[Obstacle] = []
    for feature in payload["features"]:
        coords = [tuple(pt) for pt in feature["geometry"]["coordinates"][0]]
        obstacles.append(
            Obstacle(
                polygon=coords,
                type=feature["properties"].get("type", "obstacle"),
                buffer_m=feature["properties"].get("buffer_m", 0.0),
            )
        )
    return obstacles


def load_roads(path: Path | None = None) -> Dict[str, List[Coordinate]]:
    source = path or DATA_DIR / "roads.geojson"
    with source.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    road_network: Dict[str, List[Coordinate]] = {}
    for feature in payload["features"]:
        road_id = feature["properties"]["id"]
        road_network[road_id] = [tuple(pt) for pt in feature["geometry"]["coordinates"]]
    return road_network


def obstacle_polygons(obstacles: Iterable[Obstacle]) -> List[Polygon]:
    polys: List[Polygon] = []
    for obstacle in obstacles:
        polygon = Polygon(obstacle.polygon)
        if obstacle.buffer_m > 0:
            buffer_deg = obstacle.buffer_m / 111_320.0
            polygon = polygon.buffer(buffer_deg)
        polys.append(polygon)
    return polys


def provenance_status() -> List[ProvenanceStatus]:
    dem = load_dem()
    landcover = load_landcover()
    datasets = {
        "dem": dem.metadata,
        "landcover": landcover.metadata,
    }
    now = datetime.now(timezone.utc)
    status: List[ProvenanceStatus] = []
    for name, meta in datasets.items():
        expired = meta.is_expired(now)
        expires_at = meta.expires_at
        status.append(ProvenanceStatus(dataset=name, expired=expired, expires_at=expires_at))
    return status


