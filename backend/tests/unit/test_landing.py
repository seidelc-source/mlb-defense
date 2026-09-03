"""Tests for the empirical landing density (services/alignment/landing.py)
and its engine wiring — the 0.3.0 serving path."""
import uuid
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.services.alignment.calibration import OutCalibrator
from app.services.alignment.engine import (
    GRID,
    STANDARD_POSITIONS,
    _shift2d,
    compute_alignment,
)
from app.services.alignment.landing import (
    LEAGUE_ARTIFACT,
    LandingDensity,
    build_landing_density,
    get_league_landing,
    hc_to_cell,
)


def _league_stub() -> LandingDensity:
    g = np.full((GRID, GRID), 1.0 / (GRID * GRID), dtype=np.float32)
    return LandingDensity(ground=g, air=g.copy(), ground_share=0.45,
                          source="league", n=1000)


class TestHcToCell:
    def test_matches_ingest_constants(self):
        # hc (125, 100) → nx=(125−25)/200=0.5, ny=1−100/200=0.5 → grid center.
        row, col = hc_to_cell(np.array([125.0]), np.array([100.0]))
        assert row[0] == round(0.5 * (GRID - 1))
        assert col[0] == round(0.5 * (GRID - 1))

    def test_clips_out_of_frame(self):
        row, col = hc_to_cell(np.array([-50.0, 500.0]), np.array([300.0, -50.0]))
        assert col[0] == 0 and row[0] == 0
        assert col[1] == GRID - 1 and row[1] == GRID - 1


class TestBuildLandingDensity:
    def test_no_balls_returns_league(self):
        league = _league_stub()
        d = build_landing_density(
            np.array([]), np.array([]), np.array([], dtype=bool), np.array([]),
            league=league)
        assert d is league

    def test_no_balls_no_league_returns_none(self):
        d = build_landing_density(
            np.array([]), np.array([]), np.array([], dtype=bool), np.array([]),
            league=None)
        assert d is None

    def test_grids_are_normalized_densities(self):
        rng = np.random.default_rng(7)
        n = 500
        d = build_landing_density(
            hc_x=rng.uniform(50, 200, n), hc_y=rng.uniform(20, 180, n),
            is_air=rng.random(n) < 0.5, season=np.full(n, 2024.0),
            league=_league_stub())
        for grid in (d.ground, d.air):
            assert grid.shape == (GRID, GRID)
            assert np.all(grid >= 0)
            assert grid.sum() == pytest.approx(1.0, abs=1e-4)
        assert 0.0 < d.ground_share < 1.0
        assert d.source == "batter"

    def test_small_sample_shrinks_toward_league(self):
        league = _league_stub()
        # 5 balls all in one spot vs 5000: the tiny sample must stay closer to
        # the (uniform) league prior than the big one does.
        def density(n):
            return build_landing_density(
                hc_x=np.full(n, 125.0), hc_y=np.full(n, 100.0),
                is_air=np.zeros(n, dtype=bool), season=np.full(n, 2024.0),
                league=league)
        small, big = density(5), density(5000)
        dev_small = np.abs(small.ground - league.ground).sum()
        dev_big = np.abs(big.ground - league.ground).sum()
        assert dev_small < dev_big

    def test_league_artifact_ships_and_loads(self):
        assert LEAGUE_ARTIFACT.exists(), "league landing artifact must be version-controlled"
        get_league_landing.cache_clear()
        league = get_league_landing()
        assert league is not None
        assert league.source == "league"
        assert league.ground.sum() == pytest.approx(1.0, abs=1e-3)
        assert league.air.sum() == pytest.approx(1.0, abs=1e-3)
        assert 0.4 < league.ground_share < 0.5


class TestShift2d:
    def test_no_wraparound(self):
        # Red-team D3: np.roll wrapped deep mass back to home plate. _shift2d
        # must DROP mass pushed past an edge instead.
        grid = np.zeros((10, 10), dtype=np.float32)
        grid[9, 5] = 1.0  # deepest row
        shifted = _shift2d(grid, 0, 3)  # push 3 deeper — off the grid
        assert shifted.sum() == 0.0

    def test_interior_shift_preserves_mass(self):
        grid = np.zeros((10, 10), dtype=np.float32)
        grid[4, 4] = 1.0
        shifted = _shift2d(grid, 2, -1)
        assert shifted[3, 6] == 1.0
        assert shifted.sum() == 1.0


class TestEngineWithLanding:
    def test_landing_density_drives_calibrated_scoring(self):
        cal = OutCalibrator.load()
        get_league_landing.cache_clear()
        league = get_league_landing()
        candidates = compute_alignment(
            spray_zones=[], fielder_profiles={}, roster={}, weather=None,
            optimize_for="balanced", top_n=3,
            calibrator=cal, landing=league,
        )
        assert candidates
        for c in candidates:
            assert 0.0 <= c.hit_pct <= 1.0
        # League-density fallback (the D1 fix) must land near the population
        # out rate (~0.69), not the uniform-grid 0.618 or the spray-model 0.745.
        std = next(c for c in candidates if c.shift_type == "standard")
        assert 0.66 < 1.0 - std.hit_pct < 0.73

    def test_without_landing_still_works(self):
        cal = OutCalibrator.load()
        m = MagicMock()
        m.fielding_zone = 1
        m.hit_pct, m.hit_count, m.sample_n = 0.3, 20, 50
        m.out_pct = 0.7
        m.groundball_pct, m.flyball_pct, m.linedrive_pct, m.popup_pct = 0.45, 0.3, 0.2, 0.05
        candidates = compute_alignment(
            spray_zones=[m], fielder_profiles={}, roster={}, weather=None,
            optimize_for="balanced", top_n=3, calibrator=cal,
        )
        assert candidates and all(0.0 <= c.hit_pct <= 1.0 for c in candidates)
