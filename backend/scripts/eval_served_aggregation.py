"""
Decisive check for the SERVED aggregation layer (ds-review 2026-09-03).

`calibrated_out_probability` aggregates the VERIFIED per-ball map g(coverage at
actual landing cell) under the 8-Gaussian spray-model landing density and a
ground/air blend. The red team's core finding (D2): that expectation is taken
under an unvalidated density, with hand-set sigmas carrying ±0.02–0.04 of
leverage — so scenario-level calibration of the served number is UNKNOWN.

This script runs the one test that settles it: score every standard-alignment
ball in the fit population with its batter's SERVED-STYLE expectation (career
recency-blended spray → landing grids; standard positions; league-average
reaches; no weather/pitcher tilt — the fit conditions), then reliability-test
served P(out) against realized outs.

PRE-REGISTERED EXPECTATION (written before running): if the aggregation
preserves calibration, ball-weighted mean served P(out) ≈ 0.690 (population
out rate) and cross-batter reliability slope ≈ 1 (accept [0.7, 1.3] — the
served values span a narrow range, so the slope is noise-sensitive). Red-team
prediction: level within ±0.03; possible slope compression (served spread
smaller than real cross-batter spread).

CAVEAT (stated in advance): spray profiles include the very balls being
evaluated (in-sample aggregation-consistency check, NOT an out-of-sample
forecast). Fine for testing whether the density+blend distorts a calibrated
input; not evidence of forecasting skill.

READ-ONLY. Usage:
    cd backend && python -m scripts.eval_served_aggregation
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid

import numpy as np
import pandas as pd
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.config import get_settings
from app.models.remaining_models import BatterSprayProfile
from app.models.pitch_appearance import PitchAppearance
from app.services.alignment import engine as E
from app.services.alignment.calibration import OutCalibrator
from app.services.spray_blend import merge_zone_rows
from scripts.eval_out_model import AIR_TRAJECTORIES, all_metrics, calibration
import app.models  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("eval_served_aggregation")

settings = get_settings()


async def load_balls_with_batter(seasons, alignment_filter: bool = True) -> pd.DataFrame:
    """Balls with batter_id. alignment_filter=True → the calibrator-fit
    population (standard-alignment, HR excluded) used for EVALUATION;
    False → all alignments, used to BUILD empirical densities (mirrors
    serving, which uses the batter's full history)."""
    from sqlalchemy import and_, or_
    is_air = PitchAppearance.ball_trajectory.in_(AIR_TRAJECTORIES)
    is_ground = PitchAppearance.ball_trajectory == "groundball"
    stmt = select(
        PitchAppearance.batter_id,
        PitchAppearance.season,
        PitchAppearance.game_id,
        PitchAppearance.hc_x,
        PitchAppearance.hc_y,
        PitchAppearance.ball_trajectory,
        PitchAppearance.general_result,
    ).where(
        PitchAppearance.general_result.in_(("hit", "out")),
        PitchAppearance.specific_result != "hr",
        PitchAppearance.hc_x.is_not(None),
        PitchAppearance.hc_y.is_not(None),
        PitchAppearance.fielding_zone.is_not(None),
        PitchAppearance.ball_trajectory.is_not(None),
    )
    if alignment_filter:
        stmt = stmt.where(or_(
            and_(is_ground, PitchAppearance.if_fielding_alignment == "Standard"),
            and_(is_air, PitchAppearance.of_fielding_alignment == "Standard"),
        ))
    if seasons:
        stmt = stmt.where(PitchAppearance.season.in_(seasons))
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(stmt)).mappings().all()
    df = pd.DataFrame(rows)
    df["y"] = (df["general_result"] == "out").astype(int)
    return df


async def load_all_spray_rows() -> dict:
    """All-scenario spray rows for every batter, grouped by player — the same
    rows AlignmentService._spray_zones(batter, None) would fetch."""
    stmt = select(BatterSprayProfile).where(
        BatterSprayProfile.pitch_type.is_(None),
        BatterSprayProfile.pitcher_hand.is_(None),
        BatterSprayProfile.pitch_speed_min.is_(None),
        BatterSprayProfile.pitch_speed_max.is_(None),
    )
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(stmt)).scalars().all()
    by_player: dict = {}
    for r in rows:
        by_player.setdefault(r.player_id, []).append(r)
    return by_player


def _standard_g_grids(cal: OutCalibrator):
    reaches = [
        E.compute_reach(uuid.uuid4(), pos, cx, cy, None, None, None)
        for pos, (cx, cy) in E.STANDARD_POSITIONS.items()
        if pos not in ("C", "P")
    ]
    # Ground grid via the served path (angular model when the artifact exists —
    # 2026-09-10 shipping experiment); air via reach circles + calibrator.
    _, cov_a = E._coverage_by_trajectory(reaches)
    return E.ground_out_grid(reaches, cal), cal.apply(cov_a, "air")


def served_p_out_per_batter(spray_by_player: dict, cal: OutCalibrator) -> dict:
    """Spray-model (legacy) serving expectation: standard positions,
    league-average reaches, no weather, no pitcher tilt."""
    Gg, Ga = _standard_g_grids(cal)
    out = {}
    for pid, rows in spray_by_player.items():
        zones = merge_zone_rows(rows, settings.spray_recency_decay)
        gl = E.build_hit_probability_grid(zones, None, trajectory="ground", density="landing")
        al = E.build_hit_probability_grid(zones, None, trajectory="air", density="landing")
        share = E.batter_ground_share(zones)
        p = share * float((gl * Gg).sum()) + (1 - share) * float((al * Ga).sum())
        out[pid] = p
    return out


def served_p_out_empirical(density_df: pd.DataFrame, cal: OutCalibrator) -> dict:
    """Empirical-landing serving expectation, mirroring the 0.3.0 serving path
    (services/alignment/landing.py): per-batter recency-weighted histograms,
    smoothed, shrunk toward the league artifact prior."""
    from app.services.alignment.landing import build_landing_density, get_league_landing
    league = get_league_landing()
    assert league is not None, "run scripts/build_league_landing.py first"
    Gg, Ga = _standard_g_grids(cal)
    is_air_all = density_df["ball_trajectory"].isin(AIR_TRAJECTORIES).to_numpy()
    out = {}
    for pid, idx in density_df.groupby("batter_id").indices.items():
        d = build_landing_density(
            hc_x=density_df["hc_x"].to_numpy(float)[idx],
            hc_y=density_df["hc_y"].to_numpy(float)[idx],
            is_air=is_air_all[idx],
            season=density_df["season"].to_numpy(float)[idx],
            league=league,
        )
        p = d.ground_share * float((d.ground * Gg).sum()) \
            + (1 - d.ground_share) * float((d.air * Ga).sum())
        out[pid] = p
    return out


def report(df: pd.DataFrame, min_balls_batter: int) -> dict:
    y = df["y"].to_numpy()
    p = df["p_served"].to_numpy()
    cal_stats = calibration(y, p)
    res = {
        "n_balls": int(len(df)),
        "n_batters": int(df["batter_id"].nunique()),
        "realized_out_rate": float(y.mean()),
        "mean_served_p_out": float(p.mean()),
        "level_bias": float(p.mean() - y.mean()),
        "metrics": all_metrics(y, p),
        "reliability": cal_stats,
        "served_p_spread": {
            "p05": float(np.percentile(p, 5)), "p50": float(np.percentile(p, 50)),
            "p95": float(np.percentile(p, 95)),
        },
    }
    # Cross-batter view: served p vs realized rate for well-sampled batters.
    g = df.groupby("batter_id").agg(
        p_served=("p_served", "first"), rate=("y", "mean"), n=("y", "size"))
    gb = g[g["n"] >= min_balls_batter]
    res["per_batter"] = {
        "min_balls": min_balls_batter,
        "n_batters": int(len(gb)),
        "pearson_served_vs_realized": float(np.corrcoef(gb["p_served"], gb["rate"])[0, 1]),
        "std_served": float(gb["p_served"].std()),
        "std_realized": float(gb["rate"].std()),
    }
    return res


async def main(seasons, min_balls_batter, out_json, mode) -> None:
    cal = OutCalibrator.load()
    df = await load_balls_with_batter(seasons)
    logger.info("Loaded %d standard-alignment balls (%d batters)",
                len(df), df["batter_id"].nunique())

    res = {"calibrator_version": cal.version, "mode": mode}

    if mode == "spray":
        spray = await load_all_spray_rows()
        logger.info("Spray profiles for %d batters", len(spray))
        p_map = served_p_out_per_batter(spray, cal)
        df["p_served"] = df["batter_id"].map(p_map)
        n_missing = int(df["p_served"].isna().sum())
        df = df.dropna(subset=["p_served"])
        logger.info("Dropped %d balls whose batter has no spray profile "
                    "(the D1 uniform-fallback path — checked separately)", n_missing)
        res["dropped_no_spray_balls"] = n_missing
        res["pooled"] = report(df, min_balls_batter)
    else:  # empirical — mirrors the 0.3.0 serving path
        density_df = await load_balls_with_batter(seasons, alignment_filter=False)
        logger.info("Density-building population: %d balls (all alignments)", len(density_df))
        p_map = served_p_out_empirical(density_df, cal)
        df["p_served"] = df["batter_id"].map(p_map)
        df = df.dropna(subset=["p_served"])
        res["pooled"] = report(df, min_balls_batter)

        # Split-half guard (pre-registered): densities from even-indexed balls
        # only; outcomes evaluated on the DISJOINT odd-indexed standard balls.
        density_df = density_df.sort_values(["batter_id", "game_id"]).reset_index(drop=True)
        density_df["parity"] = density_df.groupby("batter_id").cumcount() % 2
        half_map = served_p_out_empirical(density_df[density_df["parity"] == 0], cal)
        df_sorted = df.sort_values(["batter_id", "game_id"]).reset_index(drop=True)
        df_sorted["parity"] = df_sorted.groupby("batter_id").cumcount() % 2
        eval_half = df_sorted[df_sorted["parity"] == 1].copy()
        eval_half["p_served"] = eval_half["batter_id"].map(half_map)
        eval_half = eval_half.dropna(subset=["p_served"])
        g = eval_half.groupby("batter_id").agg(
            p_served=("p_served", "first"), rate=("y", "mean"), n=("y", "size"))
        gb = g[g["n"] >= min_balls_batter // 2]
        res["split_half_guard"] = {
            "n_batters": int(len(gb)),
            "pearson_served_vs_realized": float(np.corrcoef(gb["p_served"], gb["rate"])[0, 1]),
        }

    print(json.dumps({k: v for k, v in res.items() if k != "calibrator_version"}, indent=2))
    if out_json:
        with open(out_json, "w") as f:
            json.dump(res, f, indent=2)
        logger.info("Results → %s", out_json)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=int, nargs="+")
    parser.add_argument("--min-balls-batter", type=int, default=100)
    parser.add_argument("--mode", choices=["spray", "empirical"], default="spray")
    parser.add_argument("--out-json", type=str, default=None)
    args = parser.parse_args()
    out_json = args.out_json or (
        f"../documentation/artifacts/served_aggregation_check_{args.mode}.json")
    asyncio.run(main(args.seasons, args.min_balls_batter, out_json, args.mode))
