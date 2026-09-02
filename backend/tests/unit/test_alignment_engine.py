"""Unit tests for the alignment engine pipeline."""
import uuid
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.services.alignment.engine import (
    GRID,
    STANDARD_POSITIONS,
    ZONE_CENTERS,
    AlignmentCandidate,
    FielderReach,
    build_hit_probability_grid,
    clamp_to_legal,
    compute_alignment,
    compute_reach,
    default_positions_for_shift,
    is_legal_alignment,
    is_legal_position,
    score_alignment,
    score_custom_positions,
    suggest_shift_type,
)


def _make_spray_zone(zone: int, hit_pct: float = 0.3, hit_count: int = 20, sample_n: int = 50):
    m = MagicMock()
    m.fielding_zone = zone
    m.hit_pct = hit_pct
    m.hit_count = hit_count
    m.sample_n = sample_n
    m.out_pct = 1.0 - hit_pct
    m.groundball_pct = 0.45
    m.flyball_pct = 0.30
    m.linedrive_pct = 0.20
    m.popup_pct = 0.05
    return m


# ── build_hit_probability_grid ───────────────────────────────────────────────


class TestBuildHitProbabilityGrid:
    def test_empty_zones_returns_uniform(self):
        grid = build_hit_probability_grid([])
        assert grid.shape == (GRID, GRID)
        assert np.allclose(grid, 1.0 / (GRID * GRID))

    def test_single_zone_produces_gaussian_blob(self):
        zones = [_make_spray_zone(1, hit_pct=0.5, sample_n=100)]
        grid = build_hit_probability_grid(zones)
        assert grid.shape == (GRID, GRID)
        total = grid.sum()
        assert pytest.approx(total, abs=1e-5) == 1.0

        cx, cy = ZONE_CENTERS[1]
        peak_x = int(cx * (GRID - 1))
        peak_y = int(cy * (GRID - 1))
        assert grid[peak_y, peak_x] > grid[0, 0]

    def test_multiple_zones_normalize_to_one(self):
        zones = [_make_spray_zone(z) for z in range(1, 9)]
        grid = build_hit_probability_grid(zones)
        assert pytest.approx(grid.sum(), abs=1e-5) == 1.0

    def test_invalid_zone_skipped(self):
        zones = [_make_spray_zone(99, hit_pct=0.5, sample_n=100)]
        grid = build_hit_probability_grid(zones)
        assert grid.sum() == 0.0

    def test_wind_shifts_grid(self):
        zones = [_make_spray_zone(5, hit_pct=0.8, sample_n=200)]
        grid_no_wind = build_hit_probability_grid(zones)

        weather = MagicMock()
        weather.wind_x_component = 4.0
        weather.wind_y_component = 0.0
        grid_wind = build_hit_probability_grid(zones, weather)

        assert grid_no_wind.shape == grid_wind.shape
        argmax_no = np.unravel_index(grid_no_wind.argmax(), grid_no_wind.shape)
        argmax_w = np.unravel_index(grid_wind.argmax(), grid_wind.shape)
        assert argmax_w[1] > argmax_no[1]


# ── compute_reach ────────────────────────────────────────────────────────────


class TestComputeReach:
    def test_defaults_produce_positive_radii(self):
        pid = uuid.uuid4()
        reach = compute_reach(pid, "CF", 0.5, 0.8, None, None, None)
        assert reach.r_075s > 0
        assert reach.r_125s > reach.r_075s
        assert reach.r_300s > reach.r_225s

    def test_faster_player_has_wider_reach(self):
        pid = uuid.uuid4()
        slow = compute_reach(pid, "LF", 0.2, 0.7, sprint_speed=20.0, reaction_time=0.5, route_efficiency=80.0)
        fast = compute_reach(pid, "LF", 0.2, 0.7, sprint_speed=30.0, reaction_time=0.3, route_efficiency=95.0)
        assert fast.r_300s > slow.r_300s

    def test_high_reaction_time_shrinks_reach(self):
        pid = uuid.uuid4()
        quick = compute_reach(pid, "SS", 0.42, 0.38, 27.0, 0.2, 90.0)
        sluggish = compute_reach(pid, "SS", 0.42, 0.38, 27.0, 0.7, 90.0)
        assert quick.r_175s > sluggish.r_175s

    def test_zero_time_bucket_respects_reaction(self):
        pid = uuid.uuid4()
        reach = compute_reach(pid, "1B", 0.62, 0.28, 27.0, 1.0, 85.0)
        assert reach.r_075s == 0.0

    def test_coverage_grid_shape(self):
        pid = uuid.uuid4()
        reach = compute_reach(pid, "CF", 0.5, 0.8, 27.0, 0.4, 85.0)
        cov = reach.coverage_grid()
        assert cov.shape == (GRID, GRID)
        assert cov.max() <= 1.0
        assert cov.min() >= 0.0


# ── suggest_shift_type ───────────────────────────────────────────────────────


class TestSuggestShiftType:
    def test_empty_returns_standard(self):
        assert suggest_shift_type([]) == "standard"

    def test_pull_heavy_triggers_infield_shift(self):
        zones = [
            _make_spray_zone(1, hit_count=30),
            _make_spray_zone(2, hit_count=20),
            _make_spray_zone(5, hit_count=10),
            _make_spray_zone(6, hit_count=10),
            _make_spray_zone(7, hit_count=10),
            _make_spray_zone(8, hit_count=5),
        ]
        assert suggest_shift_type(zones) == "infield_shift"

    def test_oppo_heavy_triggers_outfield_shift(self):
        zones = [
            _make_spray_zone(1, hit_count=5),
            _make_spray_zone(3, hit_count=10),
            _make_spray_zone(7, hit_count=25),
            _make_spray_zone(8, hit_count=20),
        ]
        assert suggest_shift_type(zones) == "outfield_shift"

    def test_balanced_returns_standard(self):
        zones = [_make_spray_zone(z, hit_count=10) for z in range(1, 9)]
        assert suggest_shift_type(zones) == "standard"


# ── default_positions_for_shift ──────────────────────────────────────────────


class TestDefaultPositions:
    def test_standard_matches_constant(self):
        pos = default_positions_for_shift("standard")
        assert pos == STANDARD_POSITIONS

    def test_infield_shift_moves_second_base(self):
        pos = default_positions_for_shift("infield_shift")
        assert pos["2B"][0] > STANDARD_POSITIONS["2B"][0]

    def test_outfield_shift_moves_cf_right(self):
        pos = default_positions_for_shift("outfield_shift")
        assert pos["CF"][0] > STANDARD_POSITIONS["CF"][0]


# ── score_alignment ──────────────────────────────────────────────────────────


class TestScoreAlignment:
    def test_zero_grid_returns_low_confidence(self):
        grid = np.zeros((GRID, GRID), dtype=np.float32)
        oaa, hit, conf = score_alignment(grid, [], "balanced")
        assert oaa == 0.0
        assert hit == 0.5
        assert conf == 0.1

    def test_standard_vs_standard_is_zero_delta(self):
        zones = [_make_spray_zone(z) for z in range(1, 9)]
        grid = build_hit_probability_grid(zones)
        pid = uuid.uuid4()
        reaches = [
            FielderReach(player_id=pid, position=pos,
                         center_x=STANDARD_POSITIONS[pos][0],
                         center_y=STANDARD_POSITIONS[pos][1])
            for pos in ["1B", "2B", "SS", "3B", "LF", "CF", "RF"]
        ]
        oaa, _, _ = score_alignment(grid, reaches, "balanced")
        assert pytest.approx(oaa, abs=1e-4) == 0.0


# ── compute_alignment (integration-level unit test) ──────────────────────────


class TestComputeAlignment:
    def test_returns_sorted_candidates(self):
        zones = [_make_spray_zone(z, hit_count=15) for z in range(1, 9)]
        roster = {pos: uuid.uuid4() for pos in STANDARD_POSITIONS}
        results = compute_alignment(
            spray_zones=zones,
            fielder_profiles={},
            roster=roster,
            weather=None,
            optimize_for="balanced",
            top_n=3,
        )
        assert len(results) <= 3
        assert all(isinstance(c, AlignmentCandidate) for c in results)
        deltas = [c.oaa_delta for c in results]
        assert deltas == sorted(deltas, reverse=True)

    def test_no_spray_data_still_returns(self):
        roster = {pos: uuid.uuid4() for pos in STANDARD_POSITIONS}
        results = compute_alignment([], {}, roster, None, "balanced", 2)
        assert len(results) >= 1

    def test_all_candidates_are_legal(self):
        zones = [_make_spray_zone(z, hit_count=15) for z in range(1, 9)]
        roster = {pos: uuid.uuid4() for pos in STANDARD_POSITIONS}
        results = compute_alignment(zones, {}, roster, None, "balanced", 5)
        assert all(c.legal for c in results)

    def test_confidence_scales_with_sample_size(self):
        roster = {pos: uuid.uuid4() for pos in STANDARD_POSITIONS}
        small = compute_alignment(
            [_make_spray_zone(1, sample_n=10)], {}, roster, None, "balanced", 1
        )
        large = compute_alignment(
            [_make_spray_zone(1, sample_n=300)], {}, roster, None, "balanced", 1
        )
        assert large[0].confidence > small[0].confidence


# ── Shift legality (2023+ rules) ─────────────────────────────────────────────


class TestShiftLegality:
    def test_standard_positions_are_legal(self):
        assert is_legal_alignment(STANDARD_POSITIONS)

    def test_three_infielders_right_of_second_is_illegal(self):
        # Classic pre-2023 overshift: SS plays right of second base
        positions = STANDARD_POSITIONS.copy()
        positions["SS"] = (0.55, 0.33)
        assert not is_legal_alignment(positions)

    def test_infielder_on_outfield_grass_is_illegal(self):
        positions = STANDARD_POSITIONS.copy()
        positions["2B"] = (0.65, 0.55)  # short right field
        assert not is_legal_alignment(positions)

    def test_first_baseman_left_of_second_is_illegal(self):
        positions = STANDARD_POSITIONS.copy()
        positions["1B"] = (0.45, 0.30)
        assert not is_legal_alignment(positions)

    def test_outfielders_unrestricted_in_outfield(self):
        assert is_legal_position("LF", 0.85, 0.70)  # LF in right field: legal
        assert not is_legal_position("LF", 0.85, 0.30)  # LF on infield: illegal

    def test_clamp_pulls_ss_back_to_left_side(self):
        x, y = clamp_to_legal("SS", 0.60, 0.38)
        assert x < 0.5

    def test_clamp_keeps_infielder_on_dirt(self):
        x, y = clamp_to_legal("2B", 0.65, 0.60)
        assert y <= 0.45


# ── Park-aware bounds ────────────────────────────────────────────────────────


FENWAY_DIMS = {
    "left_field": 310, "left_center": 379, "center_field": 420,
    "right_center": 380, "right_field": 302,
}


class TestParkBounds:
    def test_outfielder_beyond_short_wall_is_illegal(self):
        # 330ft down the RF line at Fenway (wall: 302)
        import math
        r = 330 / 400
        x = 0.5 + r * math.sin(math.radians(40))
        y = r * math.cos(math.radians(40))
        assert not is_legal_position("RF", x, y, FENWAY_DIMS)
        # Same spot is fine without park context
        assert is_legal_position("RF", x, y)

    def test_deep_cf_is_legal_at_fenway(self):
        # 360ft straightaway center (wall: 420)
        assert is_legal_position("CF", 0.5, 0.9, FENWAY_DIMS)

    def test_clamp_pulls_outfielder_inside_fence(self):
        import math
        r = 330 / 400
        x = 0.5 + r * math.sin(math.radians(40))
        y = r * math.cos(math.radians(40))
        cx, cy = clamp_to_legal("RF", x, y, FENWAY_DIMS)
        clamped_r = math.hypot(cx - 0.5, cy) * 400
        assert clamped_r < 302
        assert is_legal_position("RF", cx, cy, FENWAY_DIMS)

    def test_compute_alignment_respects_park(self):
        zones = [_make_spray_zone(z, hit_count=15) for z in range(1, 9)]
        roster = {pos: uuid.uuid4() for pos in STANDARD_POSITIONS}
        results = compute_alignment(
            zones, {}, roster, None, "balanced", 5, dimensions=FENWAY_DIMS
        )
        assert all(c.legal for c in results)

    def test_custom_score_flags_position_beyond_fence(self):
        import math
        zones = [_make_spray_zone(z) for z in range(1, 9)]
        roster = {pos: uuid.uuid4() for pos in STANDARD_POSITIONS}
        positions = dict(STANDARD_POSITIONS)
        r = 330 / 400
        positions["RF"] = (
            0.5 + r * math.sin(math.radians(40)),
            r * math.cos(math.radians(40)),
        )
        result = score_custom_positions(
            positions, zones, {}, roster, None, "balanced", dimensions=FENWAY_DIMS
        )
        assert not result.legal


# ── score_custom_positions ───────────────────────────────────────────────────


class TestScoreCustomPositions:
    def test_custom_standard_scores_zero_delta(self):
        zones = [_make_spray_zone(z) for z in range(1, 9)]
        roster = {pos: uuid.uuid4() for pos in STANDARD_POSITIONS}
        result = score_custom_positions(
            custom_positions=dict(STANDARD_POSITIONS),
            spray_zones=zones,
            fielder_profiles={},
            roster=roster,
            weather=None,
            optimize_for="balanced",
        )
        assert result.shift_type == "custom"
        assert result.oaa_delta == pytest.approx(0.0, abs=1e-4)
        assert result.legal

    def test_illegal_arrangement_flagged(self):
        zones = [_make_spray_zone(z) for z in range(1, 9)]
        roster = {pos: uuid.uuid4() for pos in STANDARD_POSITIONS}
        positions = dict(STANDARD_POSITIONS)
        positions["SS"] = (0.60, 0.35)  # right of second base
        result = score_custom_positions(
            positions, zones, {}, roster, None, "balanced"
        )
        assert not result.legal


# ── Batter handedness (shift aiming) ─────────────────────────────────────────


from app.services.alignment.engine import _mirror_positions, resolve_batter_hand


class TestBatterHandedness:
    def test_resolve_batter_hand(self):
        assert resolve_batter_hand("L", "R") == "L"
        assert resolve_batter_hand("R", "L") == "R"
        # switch hitters bat opposite the pitcher
        assert resolve_batter_hand("S", "R") == "L"
        assert resolve_batter_hand("S", "L") == "R"
        assert resolve_batter_hand("S", None) == "L"  # default when unknown
        assert resolve_batter_hand(None, "R") is None

    def test_standard_alignment_is_handedness_invariant(self):
        assert default_positions_for_shift("standard", "R") == STANDARD_POSITIONS
        assert default_positions_for_shift("standard", "L") == STANDARD_POSITIONS

    def test_infield_shift_mirrors_by_hand(self):
        lh = default_positions_for_shift("infield_shift", "L")
        rh = default_positions_for_shift("infield_shift", "R")
        # LH pulls to RF (high x): 2B shades toward 1B (x > 0.5, deep right)
        assert lh["2B"][0] > 0.5
        # RH pulls to LF (low x): the shaded middle infielder sits left of 2B
        assert rh["SS"][0] < 0.5
        # both remain legal under 2023+ shift rules
        assert is_legal_alignment(lh)
        assert is_legal_alignment(rh)
        # RH template is the x-reflection of the LH template
        assert rh == _mirror_positions(lh)

    def test_none_hand_matches_canonical_left(self):
        # backward compatibility: no hand == canonical (LH/RF) geometry
        assert default_positions_for_shift("infield_shift", None) == \
            default_positions_for_shift("infield_shift", "L")

    def test_suggest_shift_type_flips_pull_side_by_hand(self):
        # heavy pull to the 3B/SS side (zones 3,4) = a right-handed pull hitter
        rh_pull = [_make_spray_zone(3, hit_count=30), _make_spray_zone(4, hit_count=30),
                   _make_spray_zone(6, hit_count=5), _make_spray_zone(7, hit_count=5)]
        assert suggest_shift_type(rh_pull, "R") == "infield_shift"
        # same spray read as a left-handed batter is NOT a pull-side infield shift
        assert suggest_shift_type(rh_pull, "L") != "infield_shift"
        # heavy pull to the 1B side (zones 1,2) is the mirror image
        lh_pull = [_make_spray_zone(1, hit_count=30), _make_spray_zone(2, hit_count=30),
                   _make_spray_zone(6, hit_count=5), _make_spray_zone(7, hit_count=5)]
        assert suggest_shift_type(lh_pull, "L") == "infield_shift"
        assert suggest_shift_type(lh_pull, "R") != "infield_shift"
