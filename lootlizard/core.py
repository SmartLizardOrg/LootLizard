"""Pure geometry and validated, normalized community map data.

All coordinates have a top-left origin and are fractions of the full map.
Distances are horizontal estimates, never travel distances or loot status.
"""

from dataclasses import dataclass
import json
import math
from pathlib import Path


def _number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: a finite number is required")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name}: a finite number is required")
    return value


def unit(value, name: str = "coordinate") -> float:
    value = _number(value, name)
    if not 0 <= value <= 1:
        raise ValueError(f"{name}: expected a value between 0 and 1")
    return value


@dataclass(frozen=True)
class Point:
    id: str
    name: str
    x: float
    y: float


@dataclass(frozen=True)
class SafeZone:
    """Detected white-ring geometry in normalized full-map coordinates."""

    center_x: float
    center_y: float
    radius: float

    def __post_init__(self):
        unit(self.center_x, "center_x")
        unit(self.center_y, "center_y")
        radius = _number(self.radius, "radius")
        if not 0 < radius <= 2:
            raise ValueError("Safe-zone radius must be greater than 0 and at most 2")

    def contains(self, x: float, y: float) -> bool:
        x, y = unit(x, "x"), unit(y, "y")
        return math.hypot(x - self.center_x, y - self.center_y) <= self.radius + 1e-12


@dataclass(frozen=True)
class MapData:
    id: str
    name: str
    size_m: float
    source: dict
    points: tuple[Point, ...]

    @classmethod
    def from_dict(cls, data: dict) -> "MapData":
        if not isinstance(data, dict):
            raise ValueError("Map data must be a JSON object")
        for key in ("id", "name"):
            if not isinstance(data.get(key), str) or not data[key].strip():
                raise ValueError(f"A non-empty {key} is required")
            if len(data[key]) > 160:
                raise ValueError(f"{key} is too long")
        size = _number(data.get("size_m"), "size_m")
        if not 100 <= size <= 100000:
            raise ValueError("size_m must be between 100 and 100000")
        source = data.get("source", {})
        if not isinstance(source, dict):
            raise ValueError("source must be an object")
        records = data.get("points")
        if not isinstance(records, list) or len(records) > 5000:
            raise ValueError("points must contain at most 5000 records")
        points, seen = [], set()
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("Each point must be an object")
            point_id, name = record.get("id"), record.get("name")
            if not isinstance(point_id, str) or not point_id or len(point_id) > 160:
                raise ValueError("Each point needs a short string id")
            if point_id in seen:
                raise ValueError(f"Duplicate point id: {point_id}")
            if not isinstance(name, str) or not name.strip() or len(name) > 160:
                raise ValueError("Each point needs a short name")
            points.append(Point(point_id, name, unit(record.get("x"), "x"), unit(record.get("y"), "y")))
            seen.add(point_id)
        return cls(data["id"], data["name"], size, source, tuple(points))

    @classmethod
    def load(cls, path: Path) -> "MapData":
        if path.stat().st_size > 2_000_000:
            raise ValueError("Map JSON exceeds the 2 MB limit")
        with path.open(encoding="utf-8-sig") as stream:
            return cls.from_dict(json.load(stream))

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "size_m": self.size_m,
                "source": self.source,
                "points": [dict(id=p.id, name=p.name, x=p.x, y=p.y) for p in self.points]}


@dataclass(frozen=True)
class Bounds:
    left: int
    top: int
    right: int
    bottom: int

    def validate(self, width: int, height: int) -> "Bounds":
        if not (0 <= self.left < self.right <= width and 0 <= self.top < self.bottom <= height):
            raise ValueError("Map bounds must be inside the image")
        if self.right - self.left < 32 or self.bottom - self.top < 32:
            raise ValueError("The selected map is too small")
        ratio = (self.right - self.left) / (self.bottom - self.top)
        if not 0.93 <= ratio <= 1.07:
            raise ValueError("Select the complete square map, not the entire game screen")
        return self

    def normalized(self, x: float, y: float) -> tuple[float, float]:
        return (unit((x - self.left) / (self.right - self.left), "x"),
                unit((y - self.top) / (self.bottom - self.top), "y"))

    def as_box(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom


def nearest(data: MapData, position: tuple[float, float], count: int = 3,
            *, zone: SafeZone | None = None) -> list[tuple[Point, float]]:
    """Sort by inside-zone status when known, then straight-line distance."""
    x, y = unit(position[0], "x"), unit(position[1], "y")
    if count < 0:
        raise ValueError("count cannot be negative")
    candidates = [(p, math.hypot(p.x - x, p.y - y) * data.size_m) for p in data.points]
    return sorted(candidates, key=lambda result: (
        0 if zone is None or zone.contains(result[0].x, result[0].y) else 1,
        result[1], result[0].id))[:count]
