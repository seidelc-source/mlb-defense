"""
Empirical per-batter landing density (ROADMAP P1, 2026-09-03).

The 2026-09-02 serving path took E[g(coverage)] under the 8-Gaussian spray
model's landing density, which the 2026-09-03 review showed inflates served
P(out) by ~+0.055 and erases batter-level signal (the Gaussians concentrate
mass at high-coverage zone centers, while ~half of real balls land at
coverage≈0 — documentation/EXPERIMENTS.md). This module builds the landing
density from the batter's actual `hc_x/hc_y` batted-ball locations instead:

  histogram on the engine grid (recency-weighted by season)
  → Gaussian smoothing → shrinkage toward the league-average density
  (empirical-Bayes style: weight n/(n+SHRINK_K)) → normalized grids.

Population matches the calibrator fit estimand: in-play hit/out balls, HR
excluded. The league prior ships as a versioned artifact
(artifacts/league_landing_v1.json, built by scripts/build_league_landing.py)
and doubles as the fallback for batters with no batted-ball history — fixing
the red team's D1 finding (uniform-grid fallback served 0.618).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

GRID = settings.alignment_grid_size

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
LEAGUE_ARTIFACT = ARTIFACT_DIR / "league_landing_v1.json"

# Smoothing bandwidth in grid cells (1 cell ≈ 4 ft) and shrinkage strength in
# effective ball count. Infrastructure defaults, disclosed in EXPERIMENTS.md —
# not tuned against the outcome metric.
SMOOTH_SIGMA_CELLS = 2.5
SHRINK_K = 200.0

AIR_TRAJECTORIES = ("flyball", "linedrive", "popup")


def hc_to_cell(hc_x: np.ndarray, hc_y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Canonical Statcast hc → engine-grid cell transform. Must stay identical
    to ingest `_fielding_zone_from_hc` and the eval harness `_hc_to_cell` —
    one shared frame is what makes the calibrator applicable."""
    nx = np.clip((np.asarray(hc_x, float) - 25.0) / 200.0, 0.0, 1.0)
    ny = np.clip(1.0 - np.asarray(hc_y, float) / 200.0, 0.0, 1.0)
    col = np.rint(nx * (GRID - 1)).astype(int)
    row = np.rint(ny * (GRID - 1)).astype(int)
    return row, col


def _gaussian_blur(grid: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return grid
    try:
        from scipy.ndimage import gaussian_filter
        return gaussian_filter(grid, sigma=sigma, mode="constant")
    except ImportError:  # pragma: no cover — scipy ships with sklearn in this venv
        radius = max(1, int(3 * sigma))
        x = np.arange(-radius, radius + 1)
        k = np.exp(-(x ** 2) / (2 * sigma ** 2))
        k /= k.sum()
        tmp = np.apply_along_axis(np.convolve, 1, grid, k, mode="same")
        return np.apply_along_axis(np.convolve, 0, tmp, k, mode="same")


@dataclass(frozen=True)
class LandingDensity:
    """Normalized landing-location densities per trajectory class, plus the
    batter's ground-ball share. ``source`` is "batter", "league", or "spray"
    (legacy Gaussian model); ``n`` is the effective ball count behind it."""

    ground: np.ndarray
    air: np.ndarray
    ground_share: float
    source: str
    n: int


def _normalize(grid: np.ndarray) -> np.ndarray:
    total = grid.sum()
    return (grid / total).astype(np.float32) if total > 0 else grid.astype(np.float32)


def build_landing_density(
    hc_x: np.ndarray,
    hc_y: np.ndarray,
    is_air: np.ndarray,
    season: np.ndarray,
    league: "LandingDensity | None",
    recency_decay: float | None = None,
    sigma: float = SMOOTH_SIGMA_CELLS,
    shrink_k: float = SHRINK_K,
) -> LandingDensity | None:
    """Empirical landing density for one batter from raw batted-ball rows.
    Returns the league prior when the batter has no usable balls, or None when
    neither exists (caller falls back to the legacy spray-model path)."""
    n = len(hc_x)
    if n == 0:
        return league
    decay = settings.spray_recency_decay if recency_decay is None else recency_decay
    season = np.asarray(season, dtype=float)
    w = decay ** (season.max() - season)
    row, col = hc_to_cell(hc_x, hc_y)
    is_air = np.asarray(is_air, dtype=bool)

    grids = {}
    weights = {}
    for name, mask in (("ground", ~is_air), ("air", is_air)):
        h = np.zeros((GRID, GRID), dtype=np.float64)
        np.add.at(h, (row[mask], col[mask]), w[mask])
        weights[name] = float(w[mask].sum())
        grids[name] = _gaussian_blur(h, sigma)

    if league is not None:
        # Shrink each class toward the league density and the share toward the
        # league share, by effective sample size.
        out = {}
        for name, prior in (("ground", league.ground), ("air", league.air)):
            # Histogram total ≈ effective ball count wn; the normalized prior
            # contributes SHRINK_K pseudo-balls → posterior ∝ wn·batter + k·league.
            blend = grids[name] + shrink_k * prior.astype(np.float64)
            out[name] = _normalize(blend)
        total_w = weights["ground"] + weights["air"]
        share = (weights["ground"] + shrink_k * league.ground_share) / (total_w + shrink_k)
    else:
        out = {name: _normalize(grids[name]) for name in ("ground", "air")}
        total_w = weights["ground"] + weights["air"]
        share = weights["ground"] / total_w if total_w > 0 else 0.44

    return LandingDensity(
        ground=out["ground"], air=out["air"],
        ground_share=float(share), source="batter", n=n,
    )


@lru_cache(maxsize=1)
def get_league_landing() -> LandingDensity | None:
    """League-average landing density artifact — the shrinkage prior and the
    no-data fallback. None (with a warning) if not built yet."""
    try:
        with open(LEAGUE_ARTIFACT) as f:
            d = json.load(f)
        return LandingDensity(
            ground=np.asarray(d["ground"], dtype=np.float32),
            air=np.asarray(d["air"], dtype=np.float32),
            ground_share=float(d["ground_share"]),
            source="league",
            n=int(d["n"]),
        )
    except FileNotFoundError:
        logger.warning(
            "League landing artifact missing (%s) — run scripts/build_league_landing.py; "
            "serving falls back to the legacy spray-model landing density.",
            LEAGUE_ARTIFACT,
        )
        return None
