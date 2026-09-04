"""Calibrate the Statcast hc_x/hc_y -> normalized-field transform (Gap 3).

Pre-registered 2026-09-04 (documentation/EXPERIMENTS.md). Fits
hit_distance_sc ~ s * ||(hc_x, hc_y) - (x0, y0)|| on air balls (grounder
hc/distance pairs are semantically inconsistent - see pre-registration) and
compares the fitted constants to the canonical transform's implied
home = (125, 200), scale = 2.0 ft/unit.

Usage:
    cd backend && python -m scripts.calibrate_hc_transform \
        --out-json ../documentation/artifacts/hc_transform_calibration.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.pitch_appearance import PitchAppearance

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("calibrate_hc_transform")

# Canonical transform under audit: nx=(hc_x-25)/200, ny=1-hc_y/200, 1.0 norm = 400 ft
ASSUMED_HOME = (125.0, 200.0)
ASSUMED_FT_PER_UNIT = 2.0
AIR = ("flyball", "linedrive", "popup")
MIN_DIST_FT = 30.0
SAMPLE = 200_000
SEED = 42
B = 200  # bootstrap fits (nonlinear fit is the expensive part)


async def load_air_balls() -> pd.DataFrame:
    stmt = select(
        PitchAppearance.hc_x,
        PitchAppearance.hc_y,
        PitchAppearance.hit_distance_sc,
        PitchAppearance.ball_trajectory,
        PitchAppearance.season,
    ).where(
        PitchAppearance.ball_trajectory.in_(AIR),
        PitchAppearance.hc_x.is_not(None),
        PitchAppearance.hc_y.is_not(None),
        PitchAppearance.hit_distance_sc.is_not(None),
        PitchAppearance.hit_distance_sc >= MIN_DIST_FT,
    )
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(stmt)).mappings().all()
    return pd.DataFrame(rows)


def fit_transform(hc_x: np.ndarray, hc_y: np.ndarray, dist: np.ndarray) -> dict:
    """Robust fit of dist = s * ||hc - home||; returns s, x0, y0, residual scale."""

    def residuals(params):
        s, x0, y0 = params
        return s * np.hypot(hc_x - x0, hc_y - y0) - dist

    res = least_squares(
        residuals, x0=[2.5, 125.0, 199.0], loss="soft_l1", f_scale=20.0, method="trf"
    )
    s, x0, y0 = res.x
    resid = residuals(res.x)
    return {
        "ft_per_unit": float(s),
        "home_x": float(x0),
        "home_y": float(y0),
        "resid_mad_ft": float(np.median(np.abs(resid))),
        "n": int(len(dist)),
    }


def landmark_table(s: float, x0: float, y0: float) -> list[dict]:
    """Where known distances land: current-normalized vs fitted-normalized radius."""
    rows = []
    for label, true_ft in [("2B bag", 127.28), ("IF depth", 150.0), ("corner wall", 330.0), ("CF wall", 400.0)]:
        hc_units = true_ft / s                    # true radial extent in hc units
        r_current = hc_units * ASSUMED_FT_PER_UNIT / 400.0  # where the canonical transform puts it
        r_true = true_ft / 400.0
        rows.append({
            "landmark": label,
            "true_ft": true_ft,
            "normalized_radius_current_transform": round(r_current, 4),
            "normalized_radius_true": round(r_true, 4),
            "error_normalized": round(r_current - r_true, 4),
            "error_ft_equivalent": round((r_current - r_true) * 400.0, 1),
        })
    return rows


def cell_change_fraction(df: pd.DataFrame, s: float, x0: float, y0: float, grid: int = 50) -> dict:
    """Fraction of air balls whose 50x50 landing cell moves under the corrected frame."""
    hx, hy = df["hc_x"].to_numpy(float), df["hc_y"].to_numpy(float)
    # current canonical
    nx_c = np.clip((hx - 25.0) / 200.0, 0, 1)
    ny_c = np.clip(1.0 - hy / 200.0, 0, 1)
    # corrected: feet from fitted home / 400, same orientation
    nx_f = np.clip(0.5 + s * (hx - x0) / 400.0, 0, 1)
    ny_f = np.clip(s * (y0 - hy) / 400.0, 0, 1)
    cell_c = (np.rint(ny_c * (grid - 1)) * grid + np.rint(nx_c * (grid - 1)))
    cell_f = (np.rint(ny_f * (grid - 1)) * grid + np.rint(nx_f * (grid - 1)))
    disp = 400.0 * np.hypot(nx_f - nx_c, ny_f - ny_c)
    return {
        "fraction_cell_changed_50x50": float(np.mean(cell_c != cell_f)),
        "median_displacement_ft_equivalent": float(np.median(disp)),
    }


async def main(out_json: str) -> None:
    rng = np.random.default_rng(SEED)
    df = await load_air_balls()
    logger.info("air balls with hc+distance: %d", len(df))
    if len(df) > SAMPLE:
        df = df.sample(SAMPLE, random_state=SEED).reset_index(drop=True)

    hx, hy, d = (df[c].to_numpy(float) for c in ("hc_x", "hc_y", "hit_distance_sc"))
    primary = fit_transform(hx, hy, d)
    logger.info("primary fit: %s", primary)

    boots = []
    for _ in range(B):
        idx = rng.integers(0, len(df), min(len(df), 20_000))
        boots.append(fit_transform(hx[idx], hy[idx], d[idx]))
    ci = {
        k: [float(np.percentile([b[k] for b in boots], q)) for q in (2.5, 97.5)]
        for k in ("ft_per_unit", "home_x", "home_y")
    }

    by_traj = {
        t: fit_transform(*(sub[c].to_numpy(float) for c in ("hc_x", "hc_y", "hit_distance_sc")))
        for t, sub in df.groupby("ball_trajectory")
    }
    by_era = {
        label: fit_transform(*(sub[c].to_numpy(float) for c in ("hc_x", "hc_y", "hit_distance_sc")))
        for label, sub in df.groupby(df["season"] <= 2020)
    }
    by_era = {("2016-2020" if k else "2021-2025"): v for k, v in by_era.items()}

    s, x0, y0 = primary["ft_per_unit"], primary["home_x"], primary["home_y"]
    scale_err = abs(s - ASSUMED_FT_PER_UNIT) / ASSUMED_FT_PER_UNIT
    home_off = float(np.hypot(x0 - ASSUMED_HOME[0], y0 - ASSUMED_HOME[1]))
    material = scale_err > 0.05 or home_off > 3.0

    results = {
        "assumed": {"home": ASSUMED_HOME, "ft_per_unit": ASSUMED_FT_PER_UNIT},
        "fitted": primary,
        "fitted_ci95": ci,
        "by_trajectory": by_traj,
        "by_era": by_era,
        "scale_error_pct": round(scale_err * 100, 1),
        "home_offset_hc_units": round(home_off, 2),
        "landmarks": landmark_table(s, x0, y0),
        "impact": cell_change_fraction(df, s, x0, y0),
        "verdict": "MATERIAL — coordinated rebuild warranted" if material else "IMMATERIAL — transform acceptable",
        "sample": int(len(df)),
        "seed": SEED,
    }
    with open(out_json, "w") as f:
        json.dump(results, f, indent=1)
    logger.info("scale error %.1f%%, home offset %.1f units → %s",
                scale_err * 100, home_off, results["verdict"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-json", default="../documentation/artifacts/hc_transform_calibration.json")
    args = parser.parse_args()
    asyncio.run(main(args.out_json))
