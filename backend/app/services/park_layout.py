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
    FEATURE_SPANS,
    GENERIC_DIMENSIONS,
    WALL_PROFILES,
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
    """Smooth wall polyline from the LF line to the RF line (legacy path —
    profile parks use build_wall_points_from_profile instead)."""
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


def synthesize_profile(dimensions: dict[str, int]) -> list[list[float]]:
    """Paneled 9-vertex profile from five dimensions for parks without a
    curated outline: the five anchors plus cosine-interpolated midpoints, so
    walls render as straight panels meeting at corners rather than one
    smooth bowl."""
    anchors = [
        (angle, float(dimensions[key]))
        for angle, key in zip(ANCHOR_ANGLES_DEG, DIMENSION_KEYS)
    ]
    profile: list[list[float]] = []
    for (a0, _), (a1, _) in zip(anchors, anchors[1:]):
        mid = (a0 + a1) / 2
        profile.append([a0, _interp_distance(a0, anchors)])
        profile.append([mid, _interp_distance(mid, anchors)])
    profile.append([anchors[-1][0], anchors[-1][1]])
    return profile


def build_wall_points_from_profile(
    profile: list[list[float]], samples: int = 48
) -> list[dict[str, Any]]:
    """Wall polyline as straight CHORDS between profile vertices (real fences
    are straight panels), densified in Cartesian space. Sample count per chord
    is proportional to chord length; every vertex is included exactly."""
    verts = [(_polar_to_norm(d, a), a, d) for a, d in profile]
    lengths = [
        math.hypot(v1[0][0] - v0[0][0], v1[0][1] - v0[0][1])
        for v0, v1 in zip(verts, verts[1:])
    ]
    total = sum(lengths) or 1.0
    points: list[dict[str, Any]] = []
    for (v0, v1), seg_len in zip(zip(verts, verts[1:]), lengths):
        n = max(2, int(round(samples * seg_len / total)) + 1)
        for i in range(n - 1):  # skip chord end; next chord provides it
            t = i / (n - 1)
            x = v0[0][0] + (v1[0][0] - v0[0][0]) * t
            y = v0[0][1] + (v1[0][1] - v0[0][1]) * t
            dx, dy = (x - 0.5) * FT_SCALE, y * FT_SCALE
            points.append({
                "angle_deg": round(math.degrees(math.atan2(dx, dy)) if (dx or dy) else 0.0, 2),
                "distance_ft": round(math.hypot(dx, dy), 1),
                "x": round(x, 4),
                "y": round(y, 4),
            })
    last = verts[-1]
    points.append({
        "angle_deg": round(last[1], 2),
        "distance_ft": round(last[2], 1),
        "x": round(last[0][0], 4),
        "y": round(last[0][1], 4),
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


def _extra_profile_markers(
    profile: list[list[float]], dimensions: dict[str, int], cap: int = 3
) -> list[dict[str, Any]]:
    """Markers at signature profile vertices that the five public dimensions
    don't already show (e.g. Oracle's 415 Triples Alley, PNC's 410 notch):
    vertices whose distance departs >10 ft from the 5-point interpolation."""
    anchors = [
        (angle, float(dimensions[key]))
        for angle, key in zip(ANCHOR_ANGLES_DEG, DIMENSION_KEYS)
    ]
    anchor_values = [float(dimensions[key]) for key in DIMENSION_KEYS]
    extras = []
    for angle, dist in profile:
        if any(abs(angle - a) < 3.0 for a in ANCHOR_ANGLES_DEG):
            continue
        # only numbers not already on screen (e.g. PNC's 410 notch), placed
        # where the wall genuinely departs from the five-point outline
        if any(abs(dist - v) <= 10.0 for v in anchor_values):
            continue
        depart = abs(dist - _interp_distance(angle, anchors))
        if depart > 10.0:
            x, y = _polar_to_norm(dist, angle)
            extras.append((depart, {
                "key": f"vertex_{int(angle)}",
                "label": str(int(dist)),
                "distance_ft": int(dist),
                "x": x,
                "y": y,
            }))
    extras.sort(key=lambda e: -e[0])
    return [m for _, m in extras[:cap]]


def build_layout(stadium: Stadium) -> dict[str, Any]:
    dimensions = stadium_dimensions(stadium)
    wall_heights = stadium.wall_heights or {}
    venue_id = str(stadium.mlb_venue_id or "")
    profile = WALL_PROFILES.get(venue_id) or synthesize_profile(dimensions)
    spans = FEATURE_SPANS.get(venue_id, {})

    feature_walls = []
    for key, height in wall_heights.items():
        if key not in DIMENSION_KEYS:
            continue
        anchor = ANCHOR_ANGLES_DEG[DIMENSION_KEYS.index(key)]
        a0, a1 = spans.get(key, [max(-45.0, anchor - 12.0), min(45.0, anchor + 12.0)])
        feature_walls.append({
            "key": key,
            "height_ft": float(height),
            "label": key.replace("_", " ").title(),
            "angle_start": float(a0),
            "angle_end": float(a1),
        })

    return {
        "stadium_id": stadium.id,
        "name": stadium.name,
        "city": stadium.city,
        "state": stadium.state,
        "roof_type": stadium.roof_type,
        "surface": stadium.surface,
        "altitude_ft": stadium.altitude_ft,
        "dimensions": dimensions,
        "wall_points": build_wall_points_from_profile(profile),
        "distance_markers": build_distance_markers(dimensions)
        + _extra_profile_markers(profile, dimensions),
        "feature_walls": feature_walls,
        "features": stadium.features or [],
        "precision": "visual_approximation",
    }
