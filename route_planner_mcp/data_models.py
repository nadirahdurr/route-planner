from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple


Coordinate = Tuple[float, float]


@dataclass(slots=True)
class GridMetadata:
    origin: Coordinate
    cell_size_m: float
    ttl_hours: int
    last_updated: datetime

    @property
    def expires_at(self) -> datetime:
        return self.last_updated + timedelta(hours=self.ttl_hours)

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return now > self.expires_at


@dataclass(slots=True)
class DEMData:
    grid: List[List[float]]
    metadata: GridMetadata

    @property
    def height(self) -> int:
        return len(self.grid)

    @property
    def width(self) -> int:
        return len(self.grid[0]) if self.grid else 0


@dataclass(slots=True)
class LandcoverClass:
    name: str
    cost_factor: float
    exposure: float
    speed_modifier: float


@dataclass(slots=True)
class LandcoverData:
    grid: List[List[str]]
    classes: Dict[str, LandcoverClass]
    metadata: GridMetadata


@dataclass(slots=True)
class Obstacle:
    polygon: List[Coordinate]
    type: str = "obstacle"
    buffer_m: float = 0.0


@dataclass(slots=True)
class RouteStep:
    segment_id: int
    coordinate: Coordinate
    slope: float
    terrain: str
    cost: float
    exposure: float
    elevation: float
    step_type: str
    km_marker: float
    label: Optional[str] = None


@dataclass(slots=True)
class RouteCandidate:
    id: str
    steps: List[RouteStep]
    distance_m: float
    ascent_m: float
    descent_m: float
    estimated_cost: float
    composite: Optional[float]
    constraints_used: Dict[str, Any]
    score_breakdown: Dict[str, float]
    uncertainty: Dict[str, float]
    coverage: Dict[str, float]
    coverage_units: str
    estimated_cost_notes: str
    hydrology_check: Dict[str, Optional[float]]
    mobility: Dict[str, Any]
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_geojson_feature(self) -> Dict[str, Any]:
        coordinates = [step.coordinate for step in self.steps]
        return {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            },
            "properties": {
                "id": self.id,
                "distance_m": self.distance_m,
                "ascent_m": self.ascent_m,
                "descent_m": self.descent_m,
                "cost": self.estimated_cost,
            },
        }


@dataclass(slots=True)
class RouteRisk:
    route_id: str
    slope_risk: float
    exposure_risk: float
    hydrology_risk: float
    weights: Dict[str, float]
    formula: str
    components: Dict[str, float]
    hydrology_check: Dict[str, Optional[float]]

    @property
    def aggregate(self) -> float:
        return (
            self.weights["slope"] * self.slope_risk
            + self.weights["exposure"] * self.exposure_risk
            + self.weights["hydrology"] * self.hydrology_risk
        )


@dataclass(slots=True)
class PaceEstimate:
    route_id: str
    travel_time_minutes: float
    mode: str
    load_kg: float
    base_speed_kmh: float
    assumptions: List[str]


@dataclass(slots=True)
class RouteSelectionConstraints:
    must_arrive_before: Optional[datetime] = None
    avoid_slope_degrees: Optional[float] = None
    prefer_low_risk: bool = True
    max_distance_m: Optional[float] = None


@dataclass(slots=True)
class RouteSelectionResult:
    selected_route: RouteCandidate
    risk: RouteRisk
    pace: PaceEstimate
    rationale: str
    constraints: Dict[str, Any]
    alternates: List[Dict[str, Any]]
    score_definition: str
    tie_breaker: str
    policy: Dict[str, Any]


@dataclass(slots=True)
class ProvenanceStatus:
    dataset: str
    expired: bool
    expires_at: Optional[datetime]


