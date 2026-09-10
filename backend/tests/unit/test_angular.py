"""Angular-corridor ground model tests (serving side, ang-v1)."""
import uuid

import numpy as np
import pytest

from app.services.alignment.angular import (
    CELL_THETA,
    DEFAULT_ARTIFACT,
    AngularGroundModel,
    get_angular_ground,
    station_angles,
)
from app.services.alignment.calibration import get_calibrator
from app.services.alignment.engine import (
    GRID,
    STANDARD_POSITIONS,
    compute_reach,
    default_positions_for_shift,
    ground_out_grid,
)


def _reaches(positions):
    return [
        compute_reach(uuid.uuid4(), pos, x, y, None, None, None)
        for pos, (x, y) in positions.items()
        if pos not in ("C", "P")
    ]


class TestGeometry:
    def test_cell_theta_symmetric_about_center(self):
        # column j mirrors column GRID-1-j about nx=0.5 exactly
        assert CELL_THETA[50, 20] == pytest.approx(-CELL_THETA[50, GRID - 1 - 20], abs=1e-9)

    def test_station_angles_mirror(self):
        std = station_angles(STANDARD_POSITIONS)
        mirrored = station_angles(
            {p: (1.0 - x, y) for p, (x, y) in STANDARD_POSITIONS.items()}
        )
        assert np.allclose(sorted(std), sorted(-mirrored), atol=1e-9)


class TestArtifact:
    def test_ships_and_loads(self):
        assert DEFAULT_ARTIFACT.exists(), "angular_ground_v1.json must be version-controlled"
        get_angular_ground.cache_clear()
        m = get_angular_ground()
        assert m is not None and m.version == "ang-v1"

    def test_monotone_decreasing_probabilities(self):
        m = AngularGroundModel.load()
        d = np.linspace(0, float(m.x.max()), 200)
        p = m.p_out(d)
        assert np.all(np.diff(p) <= 1e-12)
        assert 0.0 <= p.min() and p.max() <= 1.0
        assert p[0] > p[-1]  # near a station beats far from every station

    def test_grid_shape_and_range(self):
        m = AngularGroundModel.load()
        g = m.ground_out_grid(station_angles(STANDARD_POSITIONS))
        assert g.shape == (GRID, GRID)
        assert 0.0 <= g.min() and g.max() <= 1.0


class TestEngineIntegration:
    def test_ground_grid_uses_angular_model(self):
        cal = get_calibrator()
        g_std = ground_out_grid(_reaches(STANDARD_POSITIONS), cal)
        m = AngularGroundModel.load()
        expected = m.ground_out_grid(station_angles(STANDARD_POSITIONS))
        assert np.allclose(g_std, expected, atol=1e-6)

    def test_shifted_stations_move_the_grid(self):
        cal = get_calibrator()
        g_std = ground_out_grid(_reaches(STANDARD_POSITIONS), cal)
        shift_pos = default_positions_for_shift("infield_shift", bats="L")
        g_shift = ground_out_grid(_reaches(shift_pos), cal)
        assert not np.allclose(g_std, g_shift)

    def test_rh_mirror_mirrors_the_ground_grid(self):
        cal = get_calibrator()
        g_l = ground_out_grid(_reaches(default_positions_for_shift("infield_shift", bats="L")), cal)
        g_r = ground_out_grid(_reaches(default_positions_for_shift("infield_shift", bats="R")), cal)
        assert np.allclose(g_l, g_r[:, ::-1], atol=1e-4)
