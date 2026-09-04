"""Shift-selection signals: can any pre-specified signal beat "shift everyone"?

Pre-registered 2026-09-03 (documentation/EXPERIMENTS.md). Resolves ROADMAP
decision point A. Reuses the Part 2 within-batter policy-value estimator
(hand-adjusted arm rates, 2016-2022 grounders, >=40 balls/arm): a threshold
policy shifts the top-tau fraction of batters ordered by a signal; a signal
validates iff max_tau [V(tau) - V(always-shift)] > 0 with batter-bootstrap
95% CI excluding 0 AND the delta is positive in both era halves.

Signals (definitions/directions locked in the pre-registration):
  spray_dispersion    ascending  (most concentrated first)
  hard_grounder_share descending (hardest-hit first; >=20 EV-grounders)
  batter_sprint_speed ascending  (slowest first; fielding_profile median)

Usage:
    cd backend && python -m scripts.eval_shift_selection_signals \
        --bootstrap 1000 \
        --out-json ../documentation/artifacts/shift_selection_signals.json \
        --out-plot ../documentation/artifacts/shift_selection_signals.png
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.core.database import AsyncSessionLocal
from app.models.fielding_profile import FieldingProfile
from app.models.pitch_appearance import PitchAppearance
from app.models.player import Player
from scripts.eval_p1_part1 import GRID, SHIFT_ERA, _hc_to_cell
from scripts.eval_p1_part2 import _weighted, per_batter_table

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("eval_shift_selection")

ERA_HALVES = {"H1": (2016, 2018), "H2": (2019, 2022)}
HARD_EV_MPH = 90.0
MIN_EV_GROUNDERS = 20
HALF_MIN_PER_ARM = 20  # relaxed within-half floor (full-table floor stays 40)
TAUS = np.round(np.arange(0.05, 1.0, 0.05), 2)

SIGNALS = {
    # name -> (column, ascending?)  ascending=True means LOW values shifted first
    "spray_dispersion": ("spray_dispersion", True),
    "hard_grounder_share": ("hard_grounder_share", False),
    "batter_sprint_speed": ("batter_sprint_speed", True),
}


async def load_ground_balls_ext() -> pd.DataFrame:
    """Part 1's grounder query + season and launch_speed (frozen script untouched)."""
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
            PitchAppearance.launch_speed,
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
    row, col = _hc_to_cell(df["hc_x"].to_numpy(float), df["hc_y"].to_numpy(float))
    df["row"], df["col"] = row, col
    return df


async def load_sprint_speed() -> pd.DataFrame:
    stmt = select(FieldingProfile.player_id, FieldingProfile.sprint_speed_ft_s).where(
        FieldingProfile.season.in_(SHIFT_ERA),
        FieldingProfile.sprint_speed_ft_s.is_not(None),
    )
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(stmt)).mappings().all()
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["batter_id", "batter_sprint_speed"])
    agg = df.groupby("player_id")["sprint_speed_ft_s"].median().reset_index()
    agg.columns = ["batter_id", "batter_sprint_speed"]
    agg["batter_id"] = agg["batter_id"].astype(str)
    return agg


def batter_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Per-batter signal values from the raw grounder frame (locked definitions)."""
    nx = df["col"].to_numpy(float) / (GRID - 1)
    d = df.assign(nx=nx, is_hard=(df["launch_speed"] >= HARD_EV_MPH))
    g = d.groupby("batter_id")
    out = pd.DataFrame(
        {
            "spray_dispersion": g["nx"].std(),
            "ev_n": g["launch_speed"].count(),
            "hard_grounder_share": g.apply(
                lambda s: s.loc[s["launch_speed"].notna(), "is_hard"].mean(), include_groups=False
            ),
        }
    ).reset_index()
    out["batter_id"] = out["batter_id"].astype(str)
    out.loc[out["ev_n"] < MIN_EV_GROUNDERS, "hard_grounder_share"] = np.nan
    return out


def policy_delta(tbl: pd.DataFrame, order_col: str, ascending: bool, taus=TAUS) -> dict:
    """Sweep tau over the signal ordering; delta vs always-shift on this subset."""
    sub = tbl.dropna(subset=[order_col]).reset_index(drop=True)
    w = sub["weight"].to_numpy(float)
    rate_std = sub["rate_std"].to_numpy(float)
    rate_shift = sub["rate_shift"].to_numpy(float)
    v_shift_all = _weighted(rate_shift, w)
    ranks = sub[order_col].rank(pct=True, ascending=ascending).to_numpy()
    curve = []
    for t in taus:
        v = _weighted(np.where(ranks <= t, rate_shift, rate_std), w)
        curve.append({"tau": float(t), "v": v, "delta_per_1000": (v - v_shift_all) * 1000})
    best = max(curve, key=lambda c: c["delta_per_1000"])
    return {
        "n_batters": int(len(sub)),
        "v_always_shift_subset": v_shift_all,
        "curve": curve,
        "tau_star": best["tau"],
        "delta_per_1000": best["delta_per_1000"],
        "decisions": (ranks <= best["tau"]).tolist(),
    }


def bootstrap_delta(tbl: pd.DataFrame, order_col: str, ascending: bool, tau_star: float, B: int, rng) -> list[float]:
    """CI for delta at the full-sample tau* (decision vector fixed per batter)."""
    sub = tbl.dropna(subset=[order_col]).reset_index(drop=True)
    ranks = sub[order_col].rank(pct=True, ascending=ascending).to_numpy()
    dec = ranks <= tau_star
    w = sub["weight"].to_numpy(float)
    rate_std = sub["rate_std"].to_numpy(float)
    rate_shift = sub["rate_shift"].to_numpy(float)
    n = len(sub)
    deltas = np.empty(B)
    for b in range(B):
        idx = rng.integers(0, n, n)
        v_pol = _weighted(np.where(dec[idx], rate_shift[idx], rate_std[idx]), w[idx])
        v_all = _weighted(rate_shift[idx], w[idx])
        deltas[b] = (v_pol - v_all) * 1000
    lo, hi = np.percentile(deltas, [2.5, 97.5])
    return [float(lo), float(hi)]


def era_half_deltas(df: pd.DataFrame, sig_tbl: pd.DataFrame, order_col: str, ascending: bool, tau_star: float) -> dict:
    """Guardrail: same ordering (full-era signal) + same tau* on each era half's arm rates."""
    out = {}
    for name, (lo, hi) in ERA_HALVES.items():
        half = df[(df["season"] >= lo) & (df["season"] <= hi)]
        tbl_h = per_batter_table(half, HALF_MIN_PER_ARM)
        if tbl_h.empty:
            out[name] = None
            continue
        tbl_h = tbl_h.merge(sig_tbl, on="batter_id", how="left")
        sub = tbl_h.dropna(subset=[order_col]).reset_index(drop=True)
        if len(sub) < 30:
            out[name] = None
            continue
        ranks = sub[order_col].rank(pct=True, ascending=ascending).to_numpy()
        w = sub["weight"].to_numpy(float)
        v_pol = _weighted(
            np.where(ranks <= tau_star, sub["rate_shift"], sub["rate_std"]), w
        )
        v_all = _weighted(sub["rate_shift"].to_numpy(float), w)
        out[name] = {"n_batters": int(len(sub)), "delta_per_1000": (v_pol - v_all) * 1000}
    return out


def save_plot(results: dict, path: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 5))
    for name, res in results.items():
        xs = [c["tau"] for c in res["primary"]["curve"]]
        ys = [c["delta_per_1000"] for c in res["primary"]["curve"]]
        ax.plot(xs, ys, label=f"{name} (pre-registered dir)")
        ys_r = [c["delta_per_1000"] for c in res["reverse_diagnostic"]["curve"]]
        ax.plot(xs, ys_r, linestyle="--", alpha=0.4, label=f"{name} (reverse, diagnostic)")
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xlabel("τ — fraction of batters shifted (signal-ordered)")
    ax.set_ylabel("V(τ) − V(always-shift), outs per 1000 balls")
    ax.set_title("Shift-selection signals vs shift-everyone (within-batter policy value)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)


async def main(bootstrap_b: int, out_json: str, out_plot: str) -> None:
    rng = np.random.default_rng(42)
    df = await load_ground_balls_ext()
    logger.info("grounders loaded: %d", len(df))
    tbl = per_batter_table(df, 40)
    logger.info("batters >=40/arm: %d", len(tbl))

    sig = batter_signals(df)
    sprint = await load_sprint_speed()
    sig = sig.merge(sprint, on="batter_id", how="left")
    tbl = tbl.merge(sig, on="batter_id", how="left")

    v_shift_full = _weighted(tbl["rate_shift"].to_numpy(float), tbl["weight"].to_numpy(float))
    v_std_full = _weighted(tbl["rate_std"].to_numpy(float), tbl["weight"].to_numpy(float))

    results = {}
    for name, (col, asc) in SIGNALS.items():
        primary = policy_delta(tbl, col, asc)
        ci = bootstrap_delta(tbl, col, asc, primary["tau_star"], bootstrap_b, rng)
        halves = era_half_deltas(df, sig, col, asc, primary["tau_star"])
        reverse = policy_delta(tbl, col, not asc)
        validated = (
            primary["delta_per_1000"] > 0
            and ci[0] > 0
            and all(h and h["delta_per_1000"] > 0 for h in halves.values())
        )
        primary.pop("decisions")
        reverse.pop("decisions")
        results[name] = {
            "direction": "ascending" if asc else "descending",
            "primary": primary,
            "ci95_delta_at_tau_star": ci,
            "era_halves": halves,
            "reverse_diagnostic": reverse,
            "validated": bool(validated),
        }
        logger.info(
            "%s: n=%d tau*=%.2f delta=%+.2f/1000 CI[%+.2f,%+.2f] halves=%s validated=%s",
            name, primary["n_batters"], primary["tau_star"], primary["delta_per_1000"],
            ci[0], ci[1],
            {k: (round(v["delta_per_1000"], 2) if v else None) for k, v in halves.items()},
            validated,
        )

    out = {
        "pre_registration": "documentation/EXPERIMENTS.md 2026-09-03 shift-selection signals",
        "n_batters_full": int(len(tbl)),
        "v_always_shift": v_shift_full,
        "v_always_standard": v_std_full,
        "signals": results,
        "any_validated": any(r["validated"] for r in results.values()),
        "seed": 42,
        "bootstrap_B": bootstrap_b,
    }
    with open(out_json, "w") as f:
        json.dump(out, f, indent=1, default=float)
    save_plot(results, out_plot)
    logger.info("ANY SIGNAL VALIDATED: %s → %s", out["any_validated"],
                "investigate + PIT confirmation" if out["any_validated"]
                else "decision point A fires: shift broadly, graveyard per-batter selection")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--out-json", default="../documentation/artifacts/shift_selection_signals.json")
    parser.add_argument("--out-plot", default="../documentation/artifacts/shift_selection_signals.png")
    args = parser.parse_args()
    asyncio.run(main(args.bootstrap, args.out_json, args.out_plot))
