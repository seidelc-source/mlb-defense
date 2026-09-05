"""Pin the canonical era-aware hc transform (frame rebuild, 2026-09-04).

Constants come from the measured-distance calibration
(documentation/artifacts/hc_transform_calibration.json). If these tests fail,
the ball frame changed — zones, sprays, landing artifacts, and the calibrator
must be rebuilt together (see EXPERIMENTS.md 2026-09-04 frame rebuild entry).
"""
import numpy as np

from app.services.alignment.landing import (
    HC_ERA_BREAK,
    HC_POST2021,
    HC_PRE2021,
    hc_to_norm,
)


def test_era_constants_pinned():
    assert HC_ERA_BREAK == 2021
    assert HC_PRE2021 == (2.2203, 125.988, 208.386)
    assert HC_POST2021 == (2.3694, 125.945, 203.279)


def test_home_plate_maps_to_origin_both_eras():
    for season, (s, x0, y0) in ((2018, HC_PRE2021), (2024, HC_POST2021)):
        nx, ny = hc_to_norm(np.array([x0]), np.array([y0]), np.array([season]))
        assert abs(nx[0] - 0.5) < 1e-9
        assert abs(ny[0] - 0.0) < 1e-9


def test_scale_400ft_up_the_middle():
    # A ball 400 ft straight up the middle should land at ny = 1.0 exactly
    for season, (s, x0, y0) in ((2018, HC_PRE2021), (2024, HC_POST2021)):
        hc_y = y0 - 400.0 / s
        nx, ny = hc_to_norm(np.array([x0]), np.array([hc_y]), np.array([season]))
        assert abs(ny[0] - 1.0) < 1e-9
        assert abs(nx[0] - 0.5) < 1e-9


def test_era_break_applies_per_ball():
    # The eras differ in BOTH scale and home_y, so the same raw hc maps to
    # measurably different depths depending on season (not monotone — the
    # larger post-2021 scale is partly offset by the closer home_y).
    hc_x, hc_y = 125.9, 150.0
    nx, ny = hc_to_norm(
        np.array([hc_x, hc_x]), np.array([hc_y, hc_y]), np.array([2020, 2021])
    )
    for i, (s, x0, y0) in ((0, HC_PRE2021), (1, HC_POST2021)):
        assert ny[i] == np.clip(s * (y0 - hc_y) / 400.0, 0.0, 1.0)
    assert abs(ny[1] - ny[0]) > 0.005


def test_clipping_bounds():
    nx, ny = hc_to_norm(np.array([0.0, 260.0]), np.array([250.0, -20.0]), np.array([2024, 2024]))
    assert 0.0 <= nx.min() and nx.max() <= 1.0
    assert 0.0 <= ny.min() and ny.max() <= 1.0
