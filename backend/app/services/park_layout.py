"""
Park layout builder — turns a Stadium row's five-point wall dimensions into
a smooth wall polyline plus markers, in the app's normalized coordinates.

Coordinate convention (matches fieldCoords.ts / the alignment engine):
  - home plate at (0.5, 0), y increases toward center field
  - 1.0 normalized unit = 400 ft on BOTH axes
  - foul lines run at ±45°

Because real walls range from ~302 ft lines to 420 ft center, wall points may
fall slightly outside [0, 1] (e.g. Wrigley's 355 ft lines, Coors' 415 ft CF).
The frontend pads its viewBox to accommodate ~[-0.15, 1.15].
"""
from __future__ import annotations

import math
from typing import Any

from app.models.stadium import Stadium
from app.services.park_data import (
    DIMENSION_KEYS,
    GENERIC_DIMENSIONS,
    dimension_map,
)

FT_SCALE = 400.0  # 1.0 normalized = 400 ft (both axes)

# Anchor angles for the five public dimensions, degrees off the CF axis
# (negative = left field side).
ANCHOR_ANGLES_DEG = [-45.0, -22.5, 0.0, 22.5, 45.0]

WALL_SAMPLES = 33  # points along the full polyline (includes both corners)


def _polar_to_norm(distance_ft: float, angle_deg: float) -> tuple[float, float]:
    theta = math.radians(angle_deg)
    r = distance_ft / FT_SCALE
    return (round(0.5 + r * math.sin(theta), 4), round(r * math.cos(theta), 4))


def _interp_distance(angle_deg: float, anchors: list[tuple[float, float]]) -> float:
    """Cosine-smooth interpolation of wall distance at an angle.

    anchors: [(angle_deg, distance_ft)] sorted by angle, covering the query.
    """
    if angle_deg <= anchors[0][0]:
        return anchors[0][1]
    if angle_deg >= anchors[-1][0]:
        return anchors[-1][1]
    for (a0, d0), (a1, d1) in zip(anchors, anchors[1:]):
        if a0 <= angle_deg <= a1:
            t = (angle_deg - a0) / (a1 - a0)
            smooth = (1 - math.cos(math.pi * t)) / 2
            return d0 + (d1 - d0) * smooth
    return anchors[-1][1]


def stadium_dimensions(stadium: Stadium) -> dict[str, int]:
    """Five-point dimensions from the row, generic fallbacks where null."""
    values = [
        stadium.left_line_ft or GENERIC_DIMENSIONS[0],
        stadium.left_center_ft or GENERIC_DIMENSIONS[1],
        stadium.center_ft or GENERIC_DIMENSIONS[2],
        stadium.right_center_ft or GENERIC_DIMENSIONS[3],
        stadium.right_line_ft or GENERIC_DIMENSIONS[4],
    ]
    return dimension_map(values)


def build_wall_points(dimensions: dict[str, int], samples: int = WALL_SAMPLES) -> list[dict[str, Any]]:
    """Smooth wall polyline from the LF line to the RF line."""
    anchors = [
        (angle, float(dimensions[key]))
        for angle, key in zip(ANCHOR_ANGLES_DEG, DIMENSION_KEYS)
    ]
    points: list[dict[str, Any]] = []
    for i in range(samples):
        angle = -45.0 + 90.0 * i / (samples - 1)
        dist = _interp_distance(angle, anchors)
        x, y = _polar_to_norm(dist, angle)
        points.append({
            "angle_deg": round(angle, 2),
            "distance_ft": round(dist, 1),
            "x": x,
            "y": y,
        })
    return points


def build_distance_markers(dimensions: dict[str, int]) -> list[dict[str, Any]]:
    markers = []
    for angle, key in zip(ANCHOR_ANGLES_DEG, DIMENSION_KEYS):
        dist = float(dimensions[key])
        x, y = _polar_to_norm(dist, angle)
        markers.append({
            "key": key,
            "label": str(int(dist)),
            "distance_ft": int(dist),
            "x": x,
            "y": y,
        })
    return markers


def wall_distance_at(dimensions: dict[str, int], x: float, y: float) -> float:
    """Wall distance (ft) along the ray from home plate through (x, y).

    Useful for clamping fielder depth inside the fence.
    """
    dx = (x - 0.5) * FT_SCALE
    dy = y * FT_SCALE
    angle = math.degrees(math.atan2(dx, dy)) if (dx or dy) else 0.0
    angle = max(-45.0, min(45.0, angle))
    anchors = [
        (a, float(dimensions[k]))
        for a, k in zip(ANCHOR_ANGLES_DEG, DIMENSION_KEYS)
    ]
    return _interp_distance(angle, anchors)


def build_layout(stadium: Stadium) -> dict[str, Any]:
    dimensions = stadium_dimensions(stadium)
    wall_heights = stadium.wall_heights or {}

    feature_walls = [
        {
            "key": key,
            "height_ft": float(height),
            "label": key.replace("_", " ").title(),
        }
        for key, height in wall_heights.items()
        if key in DIMENSION_KEYS
    ]

    return {
        "stadium_id": stadium.id,
        "name": stadium.name,
        "city": stadium.city,
        "state": stadium.state,
        "roof_type": stadium.roof_type,
        "surface": stadium.surface,
        "altitude_ft": stadium.altitude_ft,
        "dimensions": dimensions,
        "wall_points": build_wall_points(dimensions),
        "distance_markers": build_distance_markers(dimensions),
        "feature_walls": feature_walls,
        "features": stadium.features or [],
        "precision": "visual_approximation",
    }
