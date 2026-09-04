"""Reach-model cross-check vs Statcast OAA (Gap 5 / ROADMAP decision point C).

Pre-registered 2026-09-04, amended pre-run (documentation/EXPERIMENTS.md):
fielding_profile has no playing time (innings/games all 0), so actual fielding
skill comes straight from the Savant OAA leaderboards, whose
diff_success_rate (actual - positioning-adjusted estimated success rate) is
OAA PER OPPORTUNITY - playing-time-standardized by construction.

Implied quantity (shipped serving path end to end - TRUST_REPORT D5 at the
player level): delta calibrated P(out|BIP) credited to a fielder whose sprint
speed replaces the league-average at his position, standard alignment, league
landing density, calibrator v1.

Usage:
    cd backend && python -m scripts.eval_reach_vs_oaa \
        --out-json ../documentation/artifacts/reach_vs_oaa.json \
        --out-plot ../documentation/artifacts/reach_vs_oaa.png
"""

from __future__ import annotations

import argparse
import json
import logging
import uuid

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

from app.services.alignment.calibration import get_calibrator
from app.services.alignment.engine import (
    LEAGUE_GROUND_SHARE,
    STANDARD_POSITIONS,
    calibrated_out_probability,
    compute_reach,
)
from app.services.alignment.landing import get_league_landing

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("eval_reach_vs_oaa")

SEASONS = range(2016, 2026)
GROUPS = {"IF": ("2B", "SS", "3B"), "OF": ("LF", "CF", "RF"), "1B_diagnostic": ("1B",)}
FULL_SEASON_BIP = 2970  # 1350 innings x 2.2 BIP/inning; +/-30% sensitivity below
SEED = 42
B = 1000


def pct(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.rstrip("%"), errors="coerce") / 100.0


def load_leaderboards() -> pd.DataFrame:
    import pybaseball

    frames = []
    for season in SEASONS:
        oaa = pybaseball.statcast_outs_above_average(season, "all")
        if oaa is None or oaa.empty:
            logger.warning("no OAA leaderboard for %d", season)
            continue
        sprint = pybaseball.statcast_sprint_speed(season)
        oaa = oaa.assign(season=season)
        oaa["diff_rate"] = pct(oaa["diff_success_rate_formatted"])
        oaa = oaa.merge(
            sprint[["player_id", "sprint_speed"]], on="player_id", how="left"
        )
        frames.append(oaa)
        logger.info("%d: %d fielders (%d with sprint)", season, len(oaa), oaa["sprint_speed"].notna().sum())
    df = pd.concat(frames, ignore_index=True)
    df = df.rename(columns={"primary_pos_formatted": "position", "outs_above_average": "oaa"})
    df["position"] = df["position"].astype(str).str.strip()
    df = df[df["position"].isin(sum(GROUPS.values(), ()))]
    df = df.dropna(subset=["diff_rate", "sprint_speed", "oaa"])
    df["group"] = df["position"].map({p: g for g, ps in GROUPS.items() for p in ps})
    return df


def implied_delta_fn(league_sprint: dict[str, float]):
    landing = get_league_landing()
    calibrator = get_calibrator()
    if landing is None or calibrator is None:
        raise RuntimeError("league landing artifact or calibrator missing")

    def make(override_pos=None, override_speed=None):
        return [
            compute_reach(
                uuid.uuid4(), pos, x, y,
                override_speed if pos == override_pos else league_sprint.get(pos, 27.0),
                None, None,  # reaction/route: served defaults (DB all-NULL)
            )
            for pos, (x, y) in STANDARD_POSITIONS.items()
        ]

    def p_out(reaches) -> float:
        return calibrated_out_probability(
            landing.ground, landing.air, reaches, calibrator, LEAGUE_GROUND_SHARE
        )

    base = {pos: p_out(make()) for pos in STANDARD_POSITIONS}
    cache: dict[tuple[str, float], float] = {}

    def f(pos: str, sprint: float) -> float:
        key = (pos, round(float(sprint), 1))
        if key not in cache:
            cache[key] = p_out(make(pos, key[1])) - base[pos]
        return cache[key]

    return f


def cluster_bootstrap_spearman(df: pd.DataFrame, xcol: str, ycol: str, rng) -> list[float]:
    players = df["player_id"].unique()
    by_player = {p: g[[xcol, ycol]].to_numpy() for p, g in df.groupby("player_id")}
    vals = []
    for _ in range(B):
        pick = rng.choice(players, len(players), replace=True)
        arr = np.vstack([by_player[p] for p in pick])
        vals.append(spearmanr(arr[:, 0], arr[:, 1]).statistic)
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return [float(lo), float(hi)]


def save_plot(df: pd.DataFrame, path: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 5), sharey=True)
    for ax, grp in zip(axes, ("IF", "OF")):
        sub = df[df["group"] == grp]
        j = (np.random.default_rng(0).uniform(-0.004, 0.004, len(sub)))  # de-tie the 1% grid
        ax.scatter(sub["implied_per_opp"], sub["diff_rate"] + j, s=8, alpha=0.35)
        ax.axhline(0, color="k", lw=0.6)
        ax.axvline(0, color="k", lw=0.6)
        ax.set_title(f"{grp} (n={len(sub)})")
        ax.set_xlabel("engine-implied Δ success rate (per opportunity)")
    axes[0].set_ylabel("actual − estimated success rate (OAA per opportunity)")
    fig.suptitle("Reach model (sprint-speed-only, as served) vs realized OAA rate")
    fig.tight_layout()
    fig.savefig(path, dpi=150)


def main(out_json: str, out_plot: str) -> None:
    rng = np.random.default_rng(SEED)
    df = load_leaderboards()
    logger.info("rows: %d across %d seasons", len(df), df["season"].nunique())

    league_sprint = df.groupby("position")["sprint_speed"].mean().to_dict()
    logger.info("league sprint by pos: %s", {k: round(v, 2) for k, v in league_sprint.items()})

    f = implied_delta_fn(league_sprint)
    df["implied_per_bip"] = [f(p, s) for p, s in zip(df["position"], df["sprint_speed"])]

    # attempts ~= OAA / diff_rate where |diff| >= 1% -> per-position median opportunity share
    est = df[df["diff_rate"].abs() >= 0.01].copy()
    est["attempts"] = est["oaa"] / est["diff_rate"]
    attempts_med = est[est["attempts"].between(50, 1500)].groupby("position")["attempts"].median()
    opp_share = (attempts_med / FULL_SEASON_BIP).to_dict()
    logger.info("attempts median: %s", {k: int(v) for k, v in attempts_med.items()})
    df["implied_per_opp"] = [
        d / opp_share[p] if p in opp_share else np.nan
        for d, p in zip(df["implied_per_bip"], df["position"])
    ]
    df = df.dropna(subset=["implied_per_opp"])

    results: dict = {"groups": {}, "per_position": {}}
    for grp in GROUPS:
        sub = df[df["group"] == grp]
        rho = spearmanr(sub["implied_per_opp"], sub["diff_rate"]).statistic
        r = pearsonr(sub["implied_per_opp"], sub["diff_rate"]).statistic
        ci = cluster_bootstrap_spearman(sub, "implied_per_opp", "diff_rate", rng) if grp != "1B_diagnostic" else None
        results["groups"][grp] = {"n": int(len(sub)), "spearman": float(rho),
                                  "spearman_ci95": ci, "pearson": float(r)}
        logger.info("%s: n=%d spearman=%+.3f CI=%s pearson=%+.3f", grp, len(sub), rho, ci, r)
    for pos, sub in df.groupby("position"):
        results["per_position"][pos] = {
            "n": int(len(sub)),
            "spearman_rate": float(spearmanr(sub["implied_per_opp"], sub["diff_rate"]).statistic),
            "spearman_raw_oaa": float(spearmanr(sub["implied_per_opp"], sub["oaa"]).statistic),
        }

    pooled = df[df["group"].isin(("IF", "OF"))]
    slopes = {}
    for label, scale in [("primary", 1.0), ("bip_low_-30pct", 1 / 0.7), ("bip_high_+30pct", 1 / 1.3)]:
        slope, intercept = np.polyfit(pooled["implied_per_opp"] * scale, pooled["diff_rate"], 1)
        slopes[label] = {"slope": float(slope), "intercept": float(intercept)}
    results["pooled_slope"] = slopes
    logger.info("pooled slope (actual_rate ~ implied_rate): %s",
                {k: round(v["slope"], 3) for k, v in slopes.items()})

    accept = (
        results["groups"]["IF"]["spearman_ci95"][0] > 0
        and results["groups"]["OF"]["spearman_ci95"][0] > 0
        and 0.5 <= slopes["primary"]["slope"] <= 2.0
    )
    results["decision_C"] = "ACCEPT — stop geometry work" if accept else "RE-DERIVATION WARRANTED"
    results["spread_note"] = {
        "implied_per_opp_std": {g: float(df.loc[df["group"] == g, "implied_per_opp"].std()) for g in ("IF", "OF")},
        "actual_rate_std": {g: float(df.loc[df["group"] == g, "diff_rate"].std()) for g in ("IF", "OF")},
    }
    results.update({
        "seasons": [int(s) for s in sorted(df["season"].unique())],
        "full_season_bip": FULL_SEASON_BIP,
        "opp_share_by_pos": {k: float(v) for k, v in opp_share.items()},
        "league_sprint_by_pos": {k: float(v) for k, v in league_sprint.items()},
        "seed": SEED,
    })

    with open(out_json, "w") as fj:
        json.dump(results, fj, indent=1)
    save_plot(df, out_plot)
    logger.info("DECISION C: %s", results["decision_C"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-json", default="../documentation/artifacts/reach_vs_oaa.json")
    parser.add_argument("--out-plot", default="../documentation/artifacts/reach_vs_oaa.png")
    args = parser.parse_args()
    main(args.out_json, args.out_plot)
