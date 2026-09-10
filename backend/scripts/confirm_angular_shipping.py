"""Gate G3: Part 1 harness confirmation THROUGH THE SERVED PATH (ang-v1).

Per-batter shift-vs-standard deltas computed with the shipped components —
angular artifact grids (standard vs handedness-appropriate shift stations) and
the SERVED landing-density pipeline (recency weights, smoothing, league
shrinkage) — correlated against realized lift on the Part 1 harness.
Pre-registered bar (EXPERIMENTS.md 2026-09-10): pearson >= +0.20 for BOTH
hands. This gate decides claim restoration.

Usage:
    cd backend && python -m scripts.confirm_angular_shipping \
        --out-json ../documentation/artifacts/angular_shipping_confirmation.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

import numpy as np
import pandas as pd

from app.services.alignment.angular import get_angular_ground, station_angles
from app.services.alignment.engine import STANDARD_POSITIONS, default_positions_for_shift
from app.services.alignment.landing import build_landing_density, get_league_landing
from scripts.eval_p1_part1 import load_ground_balls, realized_lift

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("confirm_angular")

MIN_PER_ARM = 40
BAR = 0.20


async def main(out_json: str) -> None:
    ang = get_angular_ground()
    league = get_league_landing()
    assert ang is not None and league is not None, "artifacts missing"

    grids = {
        "std": ang.ground_out_grid(station_angles(STANDARD_POSITIONS)),
        "L": ang.ground_out_grid(station_angles(default_positions_for_shift("infield_shift", bats="L"))),
        "R": ang.ground_out_grid(station_angles(default_positions_for_shift("infield_shift", bats="R"))),
    }

    df = await load_ground_balls()
    recs = []
    for bid, sub in df.groupby("batter_id"):
        n_std = int((sub["is_shift"] == 0).sum())
        n_shf = int((sub["is_shift"] == 1).sum())
        if n_std < MIN_PER_ARM or n_shf < MIN_PER_ARM:
            continue
        r_lift, r_se = realized_lift(sub)
        if np.isnan(r_lift) or r_se == 0 or np.isnan(r_se):
            continue
        bats = sub["bats"].iloc[0] or "?"
        # Served DELTA density (G3 amendment 2026-09-10): the batter's own
        # smoothed, UNSHRUNK histogram — shrinkage stays on the level path only.
        d = build_landing_density(
            hc_x=sub["hc_x"].to_numpy(float),
            hc_y=sub["hc_y"].to_numpy(float),
            is_air=np.zeros(len(sub), dtype=bool),
            season=sub["season"].to_numpy(float),
            league=None,
            shrink_k=0.0,
        ) or league
        hand = bats if bats in ("L", "R") else "L"
        p_std = float((d.ground * grids["std"]).sum())
        p_shift = float((d.ground * grids[hand]).sum())
        recs.append({"batter_id": str(bid), "bats": bats,
                     "realized_lift": r_lift, "pred_lift_served": p_shift - p_std})
    tbl = pd.DataFrame(recs)

    per_hand = {}
    for h in ("L", "R", "S"):
        s = tbl[tbl["bats"] == h]
        per_hand[h] = {
            "n": int(len(s)),
            "pearson": float(np.corrcoef(s["pred_lift_served"], s["realized_lift"])[0, 1]),
            "pred_std": float(s["pred_lift_served"].std()),
        }
        logger.info("hand %s: n=%d pearson %+.3f", h, per_hand[h]["n"], per_hand[h]["pearson"])
    g3_pass = per_hand["L"]["pearson"] >= BAR and per_hand["R"]["pearson"] >= BAR
    logger.info("G3 (both hands >= %+.2f): %s", BAR, "PASS" if g3_pass else "FAIL")

    with open(out_json, "w") as f:
        json.dump({"pre_registration": "EXPERIMENTS.md 2026-09-10 shipping gates",
                   "bar": BAR, "per_hand": per_hand, "g3_pass": g3_pass,
                   "n_batters": int(len(tbl))}, f, indent=1)
    logger.info("→ %s", out_json)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-json", default="../documentation/artifacts/angular_shipping_confirmation.json")
    args = parser.parse_args()
    asyncio.run(main(args.out_json))
