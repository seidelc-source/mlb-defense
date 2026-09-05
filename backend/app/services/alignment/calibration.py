"""
Per-trajectory isotonic calibrator: engine coverage → calibrated P(out).

The engine's raw coverage values are VERIFIED-miscalibrated (reliability slope
~0.39 — see documentation/EXPERIMENTS.md, 2026-09-02 P0 entry). A per-trajectory
(ground/air) isotonic recalibration was validated out-of-fold (LOSO 2016–2025):
slope ≈ 0.99, beats both zone baselines on log loss with CI separation
(2026-09-02 recalibration entry, verdict PASS).

The shipped artifact is fit by ``scripts/fit_calibrator.py`` (which re-checks
the reliability gate at fit time and refuses to write a failing artifact) and
version-controlled under ``artifacts/``. Isotonic regression is applied here as
linear interpolation over the fitted thresholds — exactly what
``sklearn.IsotonicRegression.predict(out_of_bounds="clip")`` does — so serving
needs numpy only, and a golden-transform unit test pins the mapping.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
DEFAULT_ARTIFACT = ARTIFACT_DIR / "out_calibrator_v2.json"  # v2 = corrected hc frame


@dataclass(frozen=True)
class IsotonicMap:
    """A fitted monotone map stored as (x, y) threshold arrays."""

    x: np.ndarray
    y: np.ndarray

    def apply(self, p: np.ndarray | float) -> np.ndarray | float:
        # np.interp clips outside [x[0], x[-1]] to the endpoint values —
        # identical to sklearn isotonic predict with out_of_bounds="clip".
        return np.interp(p, self.x, self.y)


@dataclass(frozen=True)
class OutCalibrator:
    version: str
    method: str
    ground: IsotonicMap
    air: IsotonicMap

    def apply(self, coverage: np.ndarray | float, trajectory: str) -> np.ndarray | float:
        """Calibrated P(out) for raw combined-coverage values.

        ``trajectory`` is "ground" or "air" — the two classes the calibrator was
        fit and validated on (air = flyball/linedrive/popup).
        """
        if trajectory == "ground":
            return self.ground.apply(coverage)
        if trajectory == "air":
            return self.air.apply(coverage)
        raise ValueError(f"unknown trajectory class: {trajectory}")

    @classmethod
    def from_dict(cls, d: dict) -> "OutCalibrator":
        maps = {}
        for name in ("ground", "air"):
            c = d["calibrators"][name]
            x = np.asarray(c["x"], dtype=float)
            y = np.asarray(c["y"], dtype=float)
            if len(x) != len(y) or len(x) < 2:
                raise ValueError(f"calibrator '{name}' malformed: {len(x)} x, {len(y)} y")
            if np.any(np.diff(x) < 0) or np.any(np.diff(y) < 0):
                raise ValueError(f"calibrator '{name}' is not monotone")
            maps[name] = IsotonicMap(x=x, y=y)
        return cls(
            version=d["version"],
            method=d.get("method", "isotonic_per_trajectory"),
            ground=maps["ground"],
            air=maps["air"],
        )

    @classmethod
    def load(cls, path: Path | str = DEFAULT_ARTIFACT) -> "OutCalibrator":
        with open(path) as f:
            return cls.from_dict(json.load(f))


@lru_cache(maxsize=1)
def get_calibrator() -> OutCalibrator | None:
    """Process-wide default calibrator; None (with a loud warning) if the
    artifact is absent — the engine then falls back to raw, uncalibrated
    scoring and responses carry ``calibrator_version=null`` so consumers can
    tell the numbers are not probabilities."""
    try:
        cal = OutCalibrator.load()
        logger.info("Loaded out-probability calibrator %s", cal.version)
        return cal
    except FileNotFoundError:
        logger.warning(
            "Calibrator artifact missing (%s) — predicted_hit_pct will be RAW "
            "coverage, not a calibrated probability. Run scripts/fit_calibrator.py.",
            DEFAULT_ARTIFACT,
        )
        return None
