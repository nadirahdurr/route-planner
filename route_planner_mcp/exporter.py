from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Dict, Optional

from .data_models import RouteCandidate, RouteSelectionResult

EXPORT_DIR = Path(__file__).resolve().parent.parent / "exports"


def ensure_export_dir() -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    return EXPORT_DIR


def _sanitize_basename(candidate: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", candidate.strip())
    cleaned = cleaned.strip("-_")
    return cleaned or fallback


def export_geojson(route: RouteCandidate, base_name: str) -> Path:
    ensure_export_dir()
    feature = route.to_geojson_feature()
    collection = {"type": "FeatureCollection", "features": [feature]}
    output_path = EXPORT_DIR / f"{base_name}.geojson"
    output_path.write_text(json.dumps(collection, indent=2), encoding="utf-8")
    return output_path


def export_gpx(route: RouteCandidate, base_name: str) -> Path:
    ensure_export_dir()
    template = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Route Planner MCP" xmlns="http://www.topografix.com/GPX/1/1">
{waypoints}
  <trk>
    <name>{name}</name>
    <trkseg>
{segments}
    </trkseg>
  </trk>
</gpx>
"""
    segment_template = '      <trkpt lat="{lat}" lon="{lon}"><ele>{ele}</ele></trkpt>'
    waypoint_template = '  <wpt lat="{lat}" lon="{lon}"><name>{name}</name><desc>{desc}</desc></wpt>'
    segments = []
    waypoints = []
    for step in route.steps:
        lat, lon = step.coordinate
        segments.append(segment_template.format(lat=lat, lon=lon, ele=step.elevation))
        if step.step_type == "checkpoint" and step.label:
            waypoints.append(
                waypoint_template.format(lat=lat, lon=lon, name=step.label, desc=f"{step.terrain} {step.km_marker} km")
            )
    body = "\n".join(segments)
    waypoint_body = "\n".join(waypoints)
    xml = template.format(name=route.id, segments=body, waypoints=waypoint_body)
    output_path = EXPORT_DIR / f"{base_name}.gpx"
    output_path.write_text(xml, encoding="utf-8")
    return output_path


def export_brief(result: RouteSelectionResult, base_name: str) -> Path:
    ensure_export_dir()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    route = result.selected_route
    pace = result.pace
    risk = result.risk
    segment_steps = [step for step in route.steps if step.step_type == "segment"]
    stride = max(1, len(segment_steps) // 6) if segment_steps else 1
    checkpoints = []
    for idx, step in enumerate(segment_steps[::stride]):
        label = step.label or f"CP{idx+1}"
        checkpoints.append(
            f"- {label}: {step.coordinate[0]:.5f}, {step.coordinate[1]:.5f} via {step.terrain}"
        )
    lines = [
        f"# Mission Brief: {route.id}",
        "",
        f"_Generated {now}_",
        "",
        "## Summary",
        f"- Total distance: {route.distance_m/1000:.2f} km",
        f"- Elevation gain: {route.ascent_m:.1f} m",
        f"- Elevation loss: {route.descent_m:.1f} m",
        f"- ETA: {pace.travel_time_minutes:.1f} min ({pace.mode}, load {pace.load_kg} kg)",
        "",
        "## Risk Assessment",
        f"- Aggregate risk: {risk.aggregate:.2f}",
        f"- Slope risk: {risk.slope_risk:.2f}",
        f"- Exposure risk: {risk.exposure_risk:.2f}",
        f"- Hydrology risk: {risk.hydrology_risk:.2f}",
        f"- Weights: {risk.weights}",
        f"- Hydrology check: {risk.hydrology_check}",
        "",
        "## Key Checkpoints",
    ]
    lines.extend(checkpoints)
    lines.extend(
        [
            "",
            "## Caveats",
            f"- {result.rationale}",
        ]
    )
    output_path = EXPORT_DIR / f"{base_name}_brief.md"
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _relative_export_path(path: Path) -> str:
    try:
        return str(path.relative_to(EXPORT_DIR.parent))
    except ValueError:
        return str(path)


def _checksum_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def export_all(result: RouteSelectionResult, basename: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    base = _sanitize_basename(basename or result.selected_route.id, result.selected_route.id)
    geojson_path = export_geojson(result.selected_route, base)
    gpx_path = export_gpx(result.selected_route, base)
    brief_path = export_brief(result, base)
    return {
        "export_root": _relative_export_path(EXPORT_DIR),
        "basename": base,
        "waypoints_in_gpx": True,
        "files": {
            "geojson": {
                "path": _relative_export_path(geojson_path),
                "checksum_sha256": _checksum_sha256(geojson_path),
            },
            "gpx": {
                "path": _relative_export_path(gpx_path),
                "checksum_sha256": _checksum_sha256(gpx_path),
            },
            "brief": {
                "path": _relative_export_path(brief_path),
                "checksum_sha256": _checksum_sha256(brief_path),
            },
        },
    }


