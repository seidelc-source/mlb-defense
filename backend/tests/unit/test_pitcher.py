"""Unit tests for pitcher tendency: aggregation classifier + engine integration."""
import uuid
from unittest.mock import MagicMock

from app.services.alignment.engine import (
    INFIELD,
    compute_alignment,
    pitcher_trajectory_weights,
)
from app.services.ingest.pitcher_aggregate import classify_pitcher


def _spray_zone(zone, hit_pct=0.4, sample_n=120, gb=0.45, fb=0.30, ld=0.20, pu=0.05):
    m = MagicMock()
    m.fielding_zone = zone
    m.hit_pct = hit_pct
    m.hit_count = int(hit_pct * sample_n)
    m.sample_n = sample_n
    m.out_pct = 1.0 - hit_pct
    m.groundball_pct = gb
    m.flyball_pct = fb
    m.linedrive_pct = ld
    m.popup_pct = pu
    return m


def _pitcher(groundball_pct):
    m = MagicMock()
    m.groundball_pct = groundball_pct
    return m


class TestTrajectoryWeights:
    def test_none_is_neutral(self):
        assert pitcher_trajectory_weights(None) == (1.0, 1.0)

    def test_missing_gb_is_neutral(self):
        assert pitcher_trajectory_weights(_pitcher(None)) == (1.0, 1.0)

    def test_groundball_pitcher_tilts_to_ground(self):
        gw, aw = pitcher_trajectory_weights(_pitcher(0.58))
        assert gw > 1.0 > aw

    def test_flyball_pitcher_tilts_to_air(self):
        gw, aw = pitcher_trajectory_weights(_pitcher(0.30))
        assert aw > 1.0 > gw

    def test_weights_are_clamped(self):
        gw, aw = pitcher_trajectory_weights(_pitcher(0.95))
        assert gw <= 1.5 and aw >= 0.6


class TestClassifyPitcher:
    def test_groundball(self):
        assert classify_pitcher(0.55, 0.20, 0.18) == "groundball"

    def test_flyball(self):
        assert classify_pitcher(0.35, 0.42, 0.18) == "flyball"

    def test_strikeout(self):
        assert classify_pitcher(0.40, 0.30, 0.30) == "strikeout"

    def test_neutral(self):
        assert classify_pitcher(0.42, 0.30, 0.18) == "neutral"


class TestEngineIntegration:
    def _args(self):
        zones = [_spray_zone(z) for z in range(1, 9)]
        roster = {p: uuid.uuid4() for p in (*INFIELD, "LF", "CF", "RF")}
        profiles = {p: None for p in roster}
        return zones, roster, profiles

    def test_none_pitcher_runs_and_is_legal(self):
        zones, roster, profiles = self._args()
        cands = compute_alignment(zones, profiles, roster, None, "balanced", 3)
        assert cands and all(c.legal for c in cands)

    def test_groundball_vs_flyball_pitcher_differ(self):
        """Same batter + roster, opposite pitcher types should not produce an
        identical top recommendation — the trajectory tilt must do something."""
        zones, roster, profiles = self._args()
        gb = compute_alignment(zones, profiles, roster, None, "balanced", 3,
                               pitcher_profile=_pitcher(0.62))
        fb = compute_alignment(zones, profiles, roster, None, "balanced", 3,
                               pitcher_profile=_pitcher(0.28))
        assert gb[0].positions != fb[0].positions or gb[0].oaa_delta != fb[0].oaa_delta
