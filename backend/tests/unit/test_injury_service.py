"""Unit tests for the injury service — degradation math and categorical levels."""
import uuid
from unittest.mock import MagicMock

import pytest

from app.services.injury_service import (
    AdjustedProfile,
    InjuryService,
    _apply,
    _range_level,
    _sprint_level,
)


def _make_profile(**overrides):
    defaults = dict(
        player_id=uuid.uuid4(),
        sprint_speed_ft_s=27.5,
        sprint_speed_level=3,
        range_pct_vs_avg=65.0,
        range_level=4,
        reaction_time_s=0.40,
        reaction_time_level=2,
        arm_strength_mph=85.0,
        arm_strength_level=3,
        arm_accuracy_pct=78.0,
        arm_accuracy_level=3,
        outs_above_average=5.0,
        fielding_run_value=3.2,
        route_efficiency_pct=88.0,
        route_efficiency_level=3,
    )
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _make_injury(
    body_part="hamstring",
    severity="moderate",
    speed_factor=0.9,
    reaction_factor=0.95,
    range_factor=0.85,
    arm_strength_factor=1.0,
    arm_accuracy_factor=1.0,
):
    m = MagicMock()
    m.body_part = body_part
    m.severity = severity
    m.speed_factor = speed_factor
    m.reaction_factor = reaction_factor
    m.range_factor = range_factor
    m.arm_strength_factor = arm_strength_factor
    m.arm_accuracy_factor = arm_accuracy_factor
    return m


# ── _apply helper ────────────────────────────────────────────────────────────


class TestApplyHelper:
    def test_none_stays_none(self):
        assert _apply(None, 0.9) is None

    def test_multiplies_and_rounds(self):
        assert _apply(27.5, 0.9) == pytest.approx(24.75)

    def test_factor_one_unchanged(self):
        assert _apply(85.0, 1.0) == 85.0


# ── AdjustedProfile.from_profile ─────────────────────────────────────────────


class TestAdjustedProfileFromProfile:
    def test_copies_all_fields(self):
        profile = _make_profile()
        adj = AdjustedProfile.from_profile(profile)
        assert adj.sprint_speed_ft_s == 27.5
        assert adj.arm_strength_mph == 85.0
        assert adj.injuries_applied == []

    def test_none_fields_preserved(self):
        profile = _make_profile(sprint_speed_ft_s=None, arm_accuracy_pct=None)
        adj = AdjustedProfile.from_profile(profile)
        assert adj.sprint_speed_ft_s is None
        assert adj.arm_accuracy_pct is None


# ── InjuryService.apply_factors ──────────────────────────────────────────────


class TestApplyFactors:
    def _svc(self):
        return InjuryService.__new__(InjuryService)

    def test_no_injuries_returns_clean_copy(self):
        svc = self._svc()
        profile = _make_profile()
        adj = svc.apply_factors(profile, [])
        assert adj.sprint_speed_ft_s == 27.5
        assert adj.injuries_applied == []

    def test_single_injury_degrades_speed(self):
        svc = self._svc()
        profile = _make_profile()
        injuries = [_make_injury(speed_factor=0.9)]
        adj = svc.apply_factors(profile, injuries)
        assert adj.sprint_speed_ft_s == pytest.approx(24.75)

    def test_multiple_injuries_stack_multiplicatively(self):
        svc = self._svc()
        profile = _make_profile()
        injuries = [
            _make_injury(body_part="hamstring", speed_factor=0.9, range_factor=0.85),
            _make_injury(body_part="ankle", speed_factor=0.85, range_factor=0.90),
        ]
        adj = svc.apply_factors(profile, injuries)
        combined_speed = 0.9 * 0.85
        combined_range = 0.85 * 0.90
        assert adj.sprint_speed_ft_s == pytest.approx(round(27.5 * combined_speed, 3), abs=0.002)
        assert adj.range_pct_vs_avg == pytest.approx(round(65.0 * combined_range, 3), abs=0.002)

    def test_reaction_time_divides_not_multiplies(self):
        svc = self._svc()
        profile = _make_profile(reaction_time_s=0.40)
        injuries = [_make_injury(reaction_factor=0.8)]
        adj = svc.apply_factors(profile, injuries)
        assert adj.reaction_time_s == pytest.approx(round(0.40 / 0.8, 3))

    def test_arm_degradation(self):
        svc = self._svc()
        profile = _make_profile()
        injuries = [_make_injury(arm_strength_factor=0.75, arm_accuracy_factor=0.90)]
        adj = svc.apply_factors(profile, injuries)
        assert adj.arm_strength_mph == pytest.approx(round(85.0 * 0.75, 3))
        assert adj.arm_accuracy_pct == pytest.approx(round(78.0 * 0.90, 3))

    def test_injuries_applied_list_populated(self):
        svc = self._svc()
        profile = _make_profile()
        injuries = [
            _make_injury(body_part="hamstring", severity="moderate"),
            _make_injury(body_part="shoulder", severity="severe"),
        ]
        adj = svc.apply_factors(profile, injuries)
        assert "hamstring:moderate" in adj.injuries_applied
        assert "shoulder:severe" in adj.injuries_applied

    def test_none_speed_after_injury_stays_none(self):
        svc = self._svc()
        profile = _make_profile(sprint_speed_ft_s=None)
        injuries = [_make_injury(speed_factor=0.9)]
        adj = svc.apply_factors(profile, injuries)
        assert adj.sprint_speed_ft_s is None

    def test_categorical_levels_rederived_after_degradation(self):
        svc = self._svc()
        profile = _make_profile(sprint_speed_ft_s=19.5, range_pct_vs_avg=82.0)
        assert _sprint_level(19.5) == 4
        assert _range_level(82.0) == 5
        injuries = [_make_injury(speed_factor=0.7, range_factor=0.5)]
        adj = svc.apply_factors(profile, injuries)
        assert adj.sprint_speed_level < 4
        assert adj.range_level < 5


# ── Categorical level helpers ────────────────────────────────────────────────


class TestSprintLevel:
    def test_none(self):
        assert _sprint_level(None) is None

    @pytest.mark.parametrize("speed,expected", [
        (25.0, 4), (19.0, 4), (18.0, 3), (16.0, 3),
        (15.0, 2), (13.0, 2), (12.0, 1), (5.0, 1),
    ])
    def test_thresholds(self, speed, expected):
        assert _sprint_level(speed) == expected


class TestRangeLevel:
    def test_none(self):
        assert _range_level(None) is None

    @pytest.mark.parametrize("pct,expected", [
        (100.0, 5), (81.0, 5), (80.0, 4), (61.0, 4),
        (60.0, 3), (41.0, 3), (40.0, 2), (21.0, 2),
        (20.0, 1), (0.0, 1),
    ])
    def test_thresholds(self, pct, expected):
        assert _range_level(pct) == expected
