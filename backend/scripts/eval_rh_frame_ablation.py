"""RH direction regression: frame-component ablation (diagnosis only).

Pre-registered 2026-09-09 (documentation/EXPERIMENTS.md). Re-runs the P1
Part 1 fixed-template direction check under six locked transform variants to
isolate which component of the corrected frame breaks the RH mirrored-
template/density registration. DIAGNOSTIC: no frame change ships from here —
any correction must come from outcome-free geometric evidence, then be
confirmed on this metric (anti-tuning guard in the pre-registration).

Usage:
    cd backend && python -m scripts.eval_rh_frame_ablation \
        --out-json ../documentation/artifacts/rh_frame_ablation.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

import numpy as np
import pandas as pd

from app.services.alignment.landing import HC_POST2021, HC_PRE2021
from scripts.eval_p1_part1 import (
    GRID,
    agreement,
    build_calibrated_grids,
    load_ground_balls,
    per_batter_table,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("rh_frame_ablation")

POOLED = (2.2903, 125.950, 206.045)  # single-era fit (hc_transform_calibration.json)
MIN_PER_ARM = 40
BOOT = 200
SEED = 42


def _era(season: np.ndarray):
    post = np.asarray(season, float) >= 2021
    s = np.where(post, HC_POST2021[0], HC_PRE2021[0])
    x0 = np.where(post, HC_POST2021[1], HC_PRE2021[1])
    y0 = np.where(post, HC_POST2021[2], HC_PRE2021[2])
    return s, x0, y0


def nx_legacy(hc_x, _s, _x0):
    return np.clip((hc_x - 25.0) / 200.0, 0.0, 1.0)


def nx_corrected(hc_x, s, x0):
    return np.clip(0.5 + s * (hc_x - x0) / 400.0, 0.0, 1.0)


def ny_legacy(hc_y, _s, _y0):
    return np.clip(1.0 - hc_y / 200.0, 0.0, 1.0)


def ny_corrected(hc_y, s, y0):
    return np.clip(s * (y0 - hc_y) / 400.0, 0.0, 1.0)


def make_cells(df: pd.DataFrame, variant: str) -> tuple[np.ndarray, np.ndarray]:
    hc_x = df["hc_x"].to_numpy(float)
    hc_y = df["hc_y"].to_numpy(float)
    s, x0, y0 = _era(df["season"].to_numpy(float))
    if variant == "E1_legacy":
        nx, ny = nx_legacy(hc_x, s, x0), ny_legacy(hc_y, s, y0)
    elif variant == "E2_corrected":
        nx, ny = nx_corrected(hc_x, s, x0), ny_corrected(hc_y, s, y0)
    elif variant == "A_legacyX_correctedY":
        nx, ny = nx_legacy(hc_x, s, x0), ny_corrected(hc_y, s, y0)
    elif variant == "B_correctedX_legacyY":
        nx, ny = nx_corrected(hc_x, s, x0), ny_legacy(hc_y, s, y0)
    elif variant == "C_pooled_era":
        sp = np.full_like(s, POOLED[0])
        nx = nx_corrected(hc_x, sp, np.full_like(x0, POOLED[1]))
        ny = ny_corrected(hc_y, sp, np.full_like(y0, POOLED[2]))
    elif variant == "D_x0_125":
        nx = nx_corrected(hc_x, s, np.full_like(x0, 125.0))
        ny = ny_corrected(hc_y, s, y0)
    else:
        raise ValueError(variant)
    col = np.rint(nx * (GRID - 1)).astype(int)
    row = np.rint(ny * (GRID - 1)).astype(int)
    return row, col


VARIANTS = ["E1_legacy", "E2_corrected", "A_legacyX_correctedY",
            "B_correctedX_legacyY", "C_pooled_era", "D_x0_125"]


def run_variant(df: pd.DataFrame, variant: str, rng) -> dict:
    d = df.copy()
    d["row"], d["col"] = make_cells(d, variant)
    grids = build_calibrated_grids(d[d["is_shift"] == 0])
    tbl = per_batter_table(d, grids, MIN_PER_ARM)
    pooled = agreement(tbl, "pred_lift_fixed", BOOT, rng)
    per_hand = {}
    for hand in ("L", "R", "S"):
        s = tbl[tbl["bats"] == hand]
        per_hand[hand] = {
            "n": int(len(s)),
            "pearson": float(np.corrcoef(s["pred_lift_fixed"], s["realized_lift"])[0, 1]),
            "pred_std": float(s["pred_lift_fixed"].std()),
        }
    return {"pooled": {k: pooled[k] for k in ("n_batters", "slope", "pearson_w", "spearman", "sign_agreement")},
            "per_hand": per_hand}


async def main(out_json: str) -> None:
    rng = np.random.default_rng(SEED)
    df = await load_ground_balls()
    logger.info("ground balls: %d", len(df))
    results = {}
    for v in VARIANTS:
        results[v] = run_variant(df, v, rng)
        ph = results[v]["per_hand"]
        logger.info("%-22s pooled_pw=%+.3f | L %+.3f (std %.4f) | R %+.3f (std %.4f)",
                    v, results[v]["pooled"]["pearson_w"],
                    ph["L"]["pearson"], ph["L"]["pred_std"],
                    ph["R"]["pearson"], ph["R"]["pred_std"])
    out = {"pre_registration": "EXPERIMENTS.md 2026-09-09 RH frame ablation",
           "min_per_arm": MIN_PER_ARM, "seed": SEED, "variants": results}
    with open(out_json, "w") as f:
        json.dump(out, f, indent=1)
    logger.info("→ %s", out_json)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-json", default="../documentation/artifacts/rh_frame_ablation.json")
    args = parser.parse_args()
    asyncio.run(main(args.out_json))
