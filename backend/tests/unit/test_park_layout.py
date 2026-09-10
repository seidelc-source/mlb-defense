"""Unit tests for park layout generation (wall interpolation, markers)."""
import uuid
from unittest.mock import MagicMock

import pytest

from app.services.park_data import (
    DIMENSION_KEYS,
    GENERIC_DIMENSIONS,
    PARKS_BY_VENUE_ID,
    dimension_map,
)
from app.services.park_layout import (
    ANCHOR_ANGLES_DEG,
    FT_SCALE,
    build_distance_markers,
    build_layout,
    build_wall_points,
    stadium_dimensions,
    wall_distance_at,
)

FENWAY = dimension_map(PARKS_BY_VENUE_ID["3"]["dimensions"])     # 310/379/420/380/302
COORS = dimension_map(PARKS_BY_VENUE_ID["19"]["dimensions"])     # 347/390/415/375/350
GENERIC = dimension_map(GENERIC_DIMENSIONS)


def _make_stadium(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        name="Test Park",
        city="Testville",
        state="TS",
        roof_type="open",
        surface="grass",
        altitude_ft=10.0,
        left_line_ft=330,
        left_center_ft=375,
        center_ft=400,
        right_center_ft=375,
        right_line_ft=330,
        wall_heights=None,
        features=None,
    )
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


class TestParkData:
    def test_all_thirty_parks_present(self):
        assert len(PARKS_BY_VENUE_ID) == 30

    def test_every_park_has_five_dimensions(self):
        for venue_id, info in PARKS_BY_VENUE_ID.items():
            assert len(info["dimensions"]) == 5, venue_id
            for d in info["dimensions"]:
                assert 290 <= d <= 430, f"{venue_id}: implausible distance {d}"


class TestBuildWallPoints:
    def test_anchor_distances_match_dimensions(self):
        points = build_wall_points(FENWAY)
        by_angle = {p["angle_deg"]: p for p in points}
        for angle, key in zip(ANCHOR_ANGLES_DEG, DIMENSION_KEYS):
            assert by_angle[round(angle, 2)]["distance_ft"] == pytest.approx(
                FENWAY[key], abs=0.1
            )

    def test_polyline_spans_both_foul_lines(self):
        points = build_wall_points(GENERIC)
        assert points[0]["angle_deg"] == -45.0
        assert points[-1]["angle_deg"] == 45.0

    def test_symmetric_park_is_symmetric(self):
        points = build_wall_points(GENERIC)
        left = points[0]
        right = points[-1]
        assert left["distance_ft"] == right["distance_ft"]
        assert left["x"] == pytest.approx(1.0 - right["x"], abs=1e-3)
        assert left["y"] == pytest.approx(right["y"], abs=1e-3)

    def test_asymmetric_park_is_asymmetric(self):
        points = build_wall_points(FENWAY)
        assert points[0]["distance_ft"] != points[-1]["distance_ft"]

    def test_points_stay_in_padded_norm_range(self):
        for dims in (FENWAY, COORS, GENERIC):
            for p in build_wall_points(dims):
                assert -0.15 <= p["x"] <= 1.15
                assert 0.0 <= p["y"] <= 1.15

    def test_distances_interpolate_smoothly(self):
        points = build_wall_points(COORS)
        distances = [p["distance_ft"] for p in points]
        # No jump between consecutive samples should exceed the largest
        # anchor-to-anchor gap
        max_gap = max(abs(a - b) for a, b in zip(distances, distances[1:]))
        assert max_gap < 20


class TestDistanceMarkers:
    def test_five_markers_with_labels(self):
        markers = build_distance_markers(FENWAY)
        assert len(markers) == 5
        assert [m["distance_ft"] for m in markers] == [310, 379, 420, 380, 302]
        assert markers[2]["label"] == "420"


class TestWallDistanceAt:
    def test_straightaway_center(self):
        d = wall_distance_at(FENWAY, 0.5, 0.9)
        assert d == pytest.approx(420, abs=0.5)

    def test_down_the_lines(self):
        # A point on the LF foul line direction
        d_left = wall_distance_at(FENWAY, 0.2, 0.3)
        assert d_left < wall_distance_at(FENWAY, 0.5, 0.9)

    def test_angle_clamped_outside_fair_territory(self):
        # Far foul ground still returns the line distance, not an extrapolation
        d = wall_distance_at(GENERIC, 0.0, 0.05)
        assert d == pytest.approx(GENERIC["left_field"], abs=0.5)


class TestStadiumDimensions:
    def test_uses_row_values(self):
        stadium = _make_stadium(left_line_ft=310, center_ft=420)
        dims = stadium_dimensions(stadium)
        assert dims["left_field"] == 310
        assert dims["center_field"] == 420

    def test_fallback_for_missing_alleys(self):
        stadium = _make_stadium(left_center_ft=None, right_center_ft=None)
        dims = stadium_dimensions(stadium)
        assert dims["left_center"] == GENERIC_DIMENSIONS[1]
        assert dims["right_center"] == GENERIC_DIMENSIONS[3]


class TestBuildLayout:
    def test_full_layout_shape(self):
        stadium = _make_stadium(
            wall_heights={"left_field": 37.2}, features=["Green Monster"]
        )
        layout = build_layout(stadium)
        assert layout["name"] == "Test Park"
        assert len(layout["wall_points"]) >= 17
        assert len(layout["distance_markers"]) == 5
        assert layout["feature_walls"] == [
            {"key": "left_field", "height_ft": 37.2, "label": "Left Field",
             "angle_start": -45.0, "angle_end": -33.0}
        ]
        assert layout["features"] == ["Green Monster"]
        assert layout["precision"] == "visual_approximation"

    def test_no_extras_yields_empty_lists(self):
        layout = build_layout(_make_stadium())
        assert layout["feature_walls"] == []
        assert layout["features"] == []


# ── Curated wall profiles (2026-09-10 realism upgrade) ───────────────────────

from app.services.park_data import FEATURE_SPANS, WALL_PROFILES  # noqa: E402
from app.services.park_layout import (  # noqa: E402
    build_wall_points_from_profile,
    synthesize_profile,
)


class TestWallProfiles:
    def test_profiles_are_ordered_and_plausible(self):
        for venue_id, profile in WALL_PROFILES.items():
            angles = [a for a, _ in profile]
            assert angles == sorted(angles), venue_id
            assert angles[0] == -45.0 and angles[-1] == 45.0, venue_id
            for _, dist in profile:
                assert 290 <= dist <= 430, f"{venue_id}: implausible {dist}"

    def test_feature_spans_reference_profiled_parks_and_heights(self):
        for venue_id, spans in FEATURE_SPANS.items():
            assert venue_id in WALL_PROFILES
            heights = PARKS_BY_VENUE_ID[venue_id].get("wall_heights", {})
            for key, (a0, a1) in spans.items():
                assert key in heights, f"{venue_id}:{key} span without height"
                assert -45.0 <= a0 < a1 <= 45.0

    def test_profile_points_hit_every_vertex(self):
        profile = WALL_PROFILES["2395"]  # Oracle: 415 Triples Alley
        points = build_wall_points_from_profile(profile)
        dists = [p["distance_ft"] for p in points]
        for _, d in profile:
            assert any(abs(x - d) < 0.6 for x in dists), f"vertex {d} missing"

    def test_chords_are_straight_in_cartesian(self):
        # Sampled points between two vertices must be collinear (a chord),
        # not bowed outward like the legacy smooth interpolation.
        profile = [[-45.0, 330.0], [0.0, 400.0], [45.0, 330.0]]
        points = build_wall_points_from_profile(profile, samples=24)
        seg = [p for p in points if -45.0 < p["angle_deg"] < 0.0]
        (x0, y0) = (points[0]["x"], points[0]["y"])
        apex = next(p for p in points if p["angle_deg"] == 0.0)
        for p in seg:
            cross = (apex["x"] - x0) * (p["y"] - y0) - (apex["y"] - y0) * (p["x"] - x0)
            assert abs(cross) < 1e-3, "chord point off the straight segment"

    def test_synthesized_profile_matches_anchor_dims(self):
        profile = synthesize_profile(GENERIC)
        by_angle = {a: d for a, d in profile}
        for angle, key in zip(ANCHOR_ANGLES_DEG, DIMENSION_KEYS):
            assert by_angle[angle] == pytest.approx(GENERIC[key], abs=0.1)

    def test_layout_uses_profile_and_extra_markers_for_oracle(self):
        stadium = _make_stadium(
            mlb_venue_id="2395",
            left_line_ft=339, left_center_ft=364, center_ft=391,
            right_center_ft=415, right_line_ft=309,
            wall_heights={"right_field": 24.0},
        )
        layout = build_layout(stadium)
        dists = [p["distance_ft"] for p in layout["wall_points"]]
        assert any(abs(d - 415) < 0.6 for d in dists)  # Triples Alley vertex
        fw = layout["feature_walls"][0]
        assert fw["angle_start"] == 21.0 and fw["angle_end"] == 45.0

    def test_layout_without_profile_synthesizes_panels(self):
        stadium = _make_stadium(mlb_venue_id=None)
        layout = build_layout(stadium)
        assert layout["wall_points"][0]["angle_deg"] == -45.0
        assert layout["wall_points"][-1]["angle_deg"] == 45.0
