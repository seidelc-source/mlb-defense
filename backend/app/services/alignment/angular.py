"""Angular-corridor ground-out model (serving side).

The ground game is an angular interception problem: grounder coordinates
record where the ball was FIELDED (outs at the infield ring, hits-through at
the outfield pickup), so recorded depth is outcome-contaminated — but the
bearing from home is causally clean (DATA_KNOWLEDGE 2026-09-09). This module
serves P(out | ground ball) as a function of the minimum angular distance
from a grid cell's bearing to the alignment's infielder stations, through a
versioned isotonic artifact (fit by scripts/fit_angular_ground.py, which
enforces a LOSO reliability gate).

Validated 2026-09-09 (EXPERIMENTS.md): recovers direction for both hands on
the held-out Part 1 harness (L +0.335 / R +0.228). League-level stations only
— per-player infield reach deltas are noise vs OAA (2026-09-04).
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
DEFAULT_ARTIFACT = ARTIFACT_DIR / "angular_ground_v1.json"

INFIELD = ("1B", "2B", "SS", "3B")


def _cell_theta() -> np.ndarray:
    """Bearing of each grid cell from home (0 = up the middle, ± toward the
    lines; home at (0.5, 0) in the fielder frame)."""
    idx = np.arange(GRID) / (GRID - 1)
    nx = idx[None, :]              # columns
    ny = idx[:, None]              # rows
    return np.arctan2(nx - 0.5, np.maximum(ny, 1e-9))


CELL_THETA = _cell_theta()


def station_angles(infield_positions: dict[str, tuple[float, float]]) -> np.ndarray:
    """Bearings of the four infielder stations."""
    return np.array(
        [np.arctan2(x - 0.5, max(y, 1e-9)) for pos, (x, y) in infield_positions.items()
         if pos in INFIELD]
    )


@dataclass(frozen=True)
class AngularGroundModel:
    """Isotonic (decreasing) map: min angular distance → P(out | ground)."""

    x: np.ndarray  # increasing angular-distance thresholds (radians)
    y: np.ndarray  # P(out) at those thresholds (decreasing)
    version: str

    def p_out(self, min_angle_dist: np.ndarray) -> np.ndarray:
        return np.interp(min_angle_dist, self.x, self.y)

    def ground_out_grid(self, stations: np.ndarray) -> np.ndarray:
        """Per-cell P(out | ground) grid for an alignment's infielder stations."""
        dist = np.min(np.abs(CELL_THETA[:, :, None] - stations[None, None, :]), axis=2)
        return self.p_out(dist).astype(np.float32)

    @classmethod
    def load(cls, path: Path | None = None) -> "AngularGroundModel":
        p = path or DEFAULT_ARTIFACT
        with open(p) as f:
            d = json.load(f)
        return cls(
            x=np.asarray(d["x"], dtype=float),
            y=np.asarray(d["y"], dtype=float),
            version=str(d["version"]),
        )


@lru_cache(maxsize=1)
def get_angular_ground() -> AngularGroundModel | None:
    """Serving singleton; None (with a warning) if the artifact is missing —
    the engine then falls back to the legacy reach-circle ground branch."""
    try:
        model = AngularGroundModel.load()
        logger.info("Loaded angular ground model %s", model.version)
        return model
    except FileNotFoundError:
        logger.warning(
            "Angular ground artifact missing (%s) — run scripts/fit_angular_ground.py; "
            "serving falls back to the legacy reach-circle ground branch.",
            DEFAULT_ARTIFACT,
        )
        return None
