"""Tests for the out-probability calibrator: artifact pinning, golden
transforms, and the calibrated engine scoring path.

The golden values pin calibrator v1 (fit 2026-09-02, LOSO OOF gate slope 0.992
on 884,402 standard-alignment balls 2016–2025). If a refit changes them, that
is a NEW calibrator version — bump the artifact version and re-pin deliberately;
never loosen the tolerances to make a drifted artifact pass.
"""
import uuid
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.services.alignment.calibration import (
    DEFAULT_ARTIFACT,
    OutCalibrator,
    get_calibrator,
)
from app.services.alignment.engine import (
    LEAGUE_GROUND_SHARE,
    STANDARD_POSITIONS,
    batter_ground_share,
    compute_alignment,
    score_custom_positions,
)

PINNED_VERSION = "v1"
# g(coverage) at coverage = [0, 0.25, 0.5, 0.75, 1.0], from the shipped artifact.
GOLDEN_GROUND = [0.484045, 0.838555, 0.870521, 0.870980, 0.870980]
GOLDEN_AIR = [0.610722, 0.780660, 0.780660, 0.780660, 0.780660]


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


class TestArtifact:
    def test_artifact_is_shipped_and_loads(self):
        assert DEFAULT_ARTIFACT.exists(), "calibrator artifact must be version-controlled"
        cal = OutCalibrator.load()
        assert cal.version == PINNED_VERSION
        assert cal.method == "isotonic_per_trajectory"

    def test_default_singleton_loads(self):
        assert get_calibrator() is not None
        assert get_calibrator().version == PINNED_VERSION

    def test_artifact_records_passing_oof_gate(self):
        import json
        gate = json.load(open(DEFAULT_ARTIFACT))["oof_gate"]
        assert gate["pass"] is True
        lo, hi = gate["slope_bounds"]
        assert lo <= gate["slope"] <= hi

    def test_golden_transform_ground(self):
        cal = OutCalibrator.load()
        got = cal.apply(np.array([0.0, 0.25, 0.5, 0.75, 1.0]), "ground")
        assert np.allclose(got, GOLDEN_GROUND, atol=1e-6)

    def test_golden_transform_air(self):
        cal = OutCalibrator.load()
        got = cal.apply(np.array([0.0, 0.25, 0.5, 0.75, 1.0]), "air")
        assert np.allclose(got, GOLDEN_AIR, atol=1e-6)

    def test_maps_are_monotone_probabilities(self):
        cal = OutCalibrator.load()
        p = np.linspace(0, 1, 500)
        for traj in ("ground", "air"):
            out = cal.apply(p, traj)
            assert np.all(np.diff(out) >= 0)
            assert np.all((out >= 0) & (out <= 1))

    def test_unknown_trajectory_raises(self):
        with pytest.raises(ValueError):
            OutCalibrator.load().apply(0.5, "linedrive")


class TestBatterGroundShare:
    def test_no_zones_falls_back_to_league(self):
        assert batter_ground_share([]) == LEAGUE_GROUND_SHARE

    def test_sample_weighted_share(self):
        zones = [_make_spray_zone(1), _make_spray_zone(5)]
        assert batter_ground_share(zones) == pytest.approx(0.45)

    def test_pitcher_tilt_renormalizes(self):
        zones = [_make_spray_zone(1)]
        tilted = batter_ground_share(zones, ground_weight=1.5, air_weight=0.6)
        assert 0.45 < tilted < 1.0


class TestCalibratedEngine:
    def _run(self, spray_zones):
        cal = OutCalibrator.load()
        return compute_alignment(
            spray_zones=spray_zones,
            fielder_profiles={},
            roster={},
            weather=None,
            optimize_for="balanced",
            top_n=5,
            calibrator=cal,
        )

    def test_hit_pct_is_probability(self):
        candidates = self._run([_make_spray_zone(z) for z in (1, 2, 5, 8)])
        for c in candidates:
            assert 0.0 <= c.hit_pct <= 1.0
        # The mapped P(out) lives well inside (0, 1) — the raw coverage score's
        # near-0/near-1 collapse is what the per-cell map removes. (Scale only:
        # the absolute value is an uncalibrated index — EXPERIMENTS 2026-09-03.)
        best = candidates[0]
        assert 0.1 < 1.0 - best.hit_pct < 0.95

    def test_standard_candidate_delta_is_zero(self):
        candidates = self._run([_make_spray_zone(z) for z in (1, 2, 5, 8)])
        std = next(c for c in candidates if c.shift_type == "standard")
        assert std.oaa_delta == pytest.approx(0.0, abs=1e-9)

    def test_candidates_sorted_by_calibrated_delta(self):
        candidates = self._run([_make_spray_zone(z) for z in (1, 2, 5, 8)])
        deltas = [c.oaa_delta for c in candidates]
        assert deltas == sorted(deltas, reverse=True)

    def test_no_spray_data_still_bounded(self):
        # Bounds only. KNOWN DEFECT (red team D1, roadmap P1): this uniform-
        # fallback path serves ~0.618 vs the correct ~0.690 population rate.
        candidates = self._run([])
        assert candidates
        assert all(0.0 <= c.hit_pct <= 1.0 for c in candidates)

    def test_score_custom_standard_positions_zero_delta(self):
        cal = OutCalibrator.load()
        custom = {p: xy for p, xy in STANDARD_POSITIONS.items()}
        result = score_custom_positions(
            custom_positions=custom,
            spray_zones=[_make_spray_zone(z) for z in (1, 2, 5, 8)],
            fielder_profiles={},
            roster={},
            weather=None,
            optimize_for="balanced",
            calibrator=cal,
        )
        assert result.oaa_delta == pytest.approx(0.0, abs=1e-9)
        assert 0.0 <= result.hit_pct <= 1.0

    def test_uncalibrated_path_unchanged_without_calibrator(self):
        # bats=None + calibrator=None is the pre-wiring legacy path.
        candidates = compute_alignment(
            spray_zones=[_make_spray_zone(z) for z in (1, 2, 5, 8)],
            fielder_profiles={},
            roster={},
            weather=None,
            optimize_for="balanced",
            top_n=3,
        )
        assert candidates
        assert all(0.0 <= c.hit_pct <= 1.0 for c in candidates)
