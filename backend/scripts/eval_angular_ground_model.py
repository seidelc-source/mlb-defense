"""Angular-corridor ground model: validation-first re-derivation (2026-09-09).

Pre-registered in documentation/EXPERIMENTS.md. Ground-out model in ANGLE
space: per grounder, feature = min angular distance from the ball's bearing
(corrected frame) to the 4 infielder stations of the alignment; isotonic
feature -> P(out) fit on STANDARD-alignment grounders; the same g applied to
shift-template features gives per-batter predicted lift, checked against the
Part 1 realized-lift harness (held out - never fit on). League-level stations
only (IF per-player reach deltas are noise vs OAA, 2026-09-04).

Usage:
    cd backend && python -m scripts.eval_angular_ground_model \
        --out-json ../documentation/artifacts/angular_ground_model.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.core.database import AsyncSessionLocal
from app.models.pitch_appearance import PitchAppearance
from app.models.player import Player
from app.services.alignment.landing import hc_to_norm
from scripts.eval_out_model import auc, log_loss
from scripts.eval_p1_part1 import (
    SHIFT_ERA,
    _infield_from_engine,
    agreement,
    realized_lift,
)
import app.models  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("angular_ground")

MIN_NY = 0.05
MIN_PER_ARM = 40
BOOT = 1000
SEED = 42


async def load() -> pd.DataFrame:
    Batter = aliased(Player)
    Pitcher = aliased(Player)
    stmt = (
        select(
            PitchAppearance.batter_id,
            Batter.bats.label("bats"),
            Pitcher.throws.label("pitcher_hand"),
            PitchAppearance.if_fielding_alignment.label("align"),
            PitchAppearance.general_result,
            PitchAppearance.hc_x,
            PitchAppearance.hc_y,
            PitchAppearance.season,
            PitchAppearance.fielding_zone,
        )
        .join(Batter, Batter.id == PitchAppearance.batter_id, isouter=True)
        .join(Pitcher, Pitcher.id == PitchAppearance.pitcher_id, isouter=True)
        .where(
            PitchAppearance.season.in_(SHIFT_ERA),
            PitchAppearance.ball_trajectory == "groundball",
            PitchAppearance.if_fielding_alignment.in_(("Standard", "Infield shift")),
            PitchAppearance.general_result.in_(("hit", "out")),
            PitchAppearance.hc_x.is_not(None),
            PitchAppearance.hc_y.is_not(None),
            PitchAppearance.batter_id.is_not(None),
        )
    )
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(stmt)).mappings().all()
    df = pd.DataFrame(rows)
    df["y"] = (df["general_result"] == "out").astype(int)
    df["is_shift"] = (df["align"] == "Infield shift").astype(int)
    nx, ny = hc_to_norm(
        df["hc_x"].to_numpy(float), df["hc_y"].to_numpy(float), df["season"].to_numpy(float)
    )
    df["theta"] = np.arctan2(nx - 0.5, ny)
    df["ny"] = ny
    n0 = len(df)
    df = df[df["ny"] >= MIN_NY].reset_index(drop=True)
    logger.info("grounders: %d (excluded %d with ny < %.2f)", len(df), n0 - len(df), MIN_NY)
    return df


def station_angles(shift_type: str, bats: str | None) -> np.ndarray:
    pos = _infield_from_engine(shift_type, bats)
    return np.array([np.arctan2(x - 0.5, y) for x, y in pos.values()])


def min_angle_dist(theta: np.ndarray, stations: np.ndarray) -> np.ndarray:
    return np.min(np.abs(theta[:, None] - stations[None, :]), axis=1)


def fit_g(feature: np.ndarray, y: np.ndarray) -> IsotonicRegression:
    iso = IsotonicRegression(increasing=False, out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(feature, y)
    return iso


def main_sync(df: pd.DataFrame, out_json: str) -> None:
    rng = np.random.default_rng(SEED)
    std_stations = station_angles("standard", None)
    shift_stations = {b: station_angles("infield_shift", b) for b in ("L", "R")}

    # ── Descriptive guardrail: LOSO on standard grounders, angular vs zone ────
    std = df[df["is_shift"] == 0]
    losolog = {"angular": [], "zone": []}
    for s in sorted(std["season"].unique()):
        tr, te = std[std["season"] != s], std[std["season"] == s]
        g = fit_g(min_angle_dist(tr["theta"].to_numpy(), std_stations), tr["y"].to_numpy())
        p_ang = g.predict(min_angle_dist(te["theta"].to_numpy(), std_stations))
        zr = tr.groupby("fielding_zone")["y"].mean()
        p_zone = te["fielding_zone"].map(zr).fillna(tr["y"].mean()).to_numpy(float)
        yte = te["y"].to_numpy()
        losolog["angular"].append({"season": int(s), "ll": log_loss(yte, np.clip(p_ang, 1e-6, 1 - 1e-6)),
                                   "auc": auc(yte, p_ang)})
        losolog["zone"].append({"season": int(s), "ll": log_loss(yte, np.clip(p_zone, 1e-6, 1 - 1e-6)),
                                "auc": auc(yte, p_zone)})
    ll_ang = float(np.mean([r["ll"] for r in losolog["angular"]]))
    ll_zone = float(np.mean([r["ll"] for r in losolog["zone"]]))
    auc_ang = float(np.mean([r["auc"] for r in losolog["angular"]]))
    auc_zone = float(np.mean([r["auc"] for r in losolog["zone"]]))
    guardrail_pass = ll_ang <= ll_zone + 0.002
    logger.info("LOSO grounders — angular ll %.4f auc %.4f | zone ll %.4f auc %.4f | guardrail %s",
                ll_ang, auc_ang, ll_zone, auc_zone, "PASS" if guardrail_pass else "FAIL")

    # ── Prescriptive: per-batter predicted lift vs realized (held-out) ────────
    g_full = fit_g(min_angle_dist(std["theta"].to_numpy(), std_stations), std["y"].to_numpy())
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
        theta = sub["theta"].to_numpy()
        p_std = g_full.predict(min_angle_dist(theta, std_stations)).mean()
        hand = bats if bats in ("L", "R") else "L"  # S handled per-PA at serve; aggregate harness limitation
        p_shift = g_full.predict(min_angle_dist(theta, shift_stations[hand])).mean()
        recs.append({"batter_id": str(bid), "bats": bats, "n_std": n_std, "n_shift": n_shf,
                     "realized_lift": r_lift, "realized_se": r_se,
                     "pred_lift_fixed": float(p_shift - p_std)})
    tbl = pd.DataFrame(recs)
    pooled = agreement(tbl, "pred_lift_fixed", BOOT, rng)
    per_hand = {}
    for h in ("L", "R", "S"):
        s = tbl[tbl["bats"] == h]
        per_hand[h] = {"n": int(len(s)),
                       "pearson": float(np.corrcoef(s["pred_lift_fixed"], s["realized_lift"])[0, 1]),
                       "pred_std": float(s["pred_lift_fixed"].std()),
                       "mean_pred": float(s["pred_lift_fixed"].mean())}
        logger.info("hand %s: n=%d pearson %+.3f (pred std %.4f, mean %+.4f)",
                    h, per_hand[h]["n"], per_hand[h]["pearson"], per_hand[h]["pred_std"], per_hand[h]["mean_pred"])
    primary_pass = per_hand["L"]["pearson"] >= 0.20 and per_hand["R"]["pearson"] >= 0.20
    logger.info("pooled: %s", {k: round(v, 4) if isinstance(v, float) else v
                               for k, v in pooled.items() if k in ("slope", "pearson_w", "spearman", "sign_agreement")})
    logger.info("PRIMARY (L>=0.20 and R>=0.20): %s | GUARDRAIL: %s",
                "PASS" if primary_pass else "FAIL", "PASS" if guardrail_pass else "FAIL")

    out = {
        "pre_registration": "EXPERIMENTS.md 2026-09-09 angular-corridor ground model",
        "n_grounders": int(len(df)),
        "descriptive_loso": {"angular_ll": ll_ang, "zone_ll": ll_zone,
                             "angular_auc": auc_ang, "zone_auc": auc_zone,
                             "per_season": losolog, "guardrail_pass": guardrail_pass},
        "prescriptive": {"pooled": pooled, "per_hand": per_hand, "primary_pass": primary_pass,
                         "n_batters": int(len(tbl))},
        "seed": SEED, "min_ny": MIN_NY,
    }
    with open(out_json, "w") as f:
        json.dump(out, f, indent=1, default=float)
    logger.info("→ %s", out_json)


async def main(out_json: str) -> None:
    df = await load()
    main_sync(df, out_json)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-json", default="../documentation/artifacts/angular_ground_model.json")
    args = parser.parse_args()
    asyncio.run(main(args.out_json))
