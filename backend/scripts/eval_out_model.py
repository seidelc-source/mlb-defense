"""
P0 evaluation harness — does the engine's out-probability surface (at the
standard alignment) predict realized out/hit on real batted balls better than
a trivial 8-zone out-rate lookup?

See documentation/EXPERIMENTS.md (2026-09-01 pre-registration) for the full
design, estimand, decision rule, and threats to validity. This script is
READ-ONLY: it never mutates the DB and makes NO engine code changes — it only
reuses engine internals to read the coverage surface.

Scope tested: P(out | standard alignment). It does NOT validate the prescriptive
oaa_delta (an unobserved counterfactual). A pass is necessary, not sufficient.

Usage:
    cd backend
    python -m scripts.eval_out_model                      # all backfilled seasons
    python -m scripts.eval_out_model --seasons 2021 2022 2023 2024
    python -m scripts.eval_out_model --bootstrap 1000 --out-json /tmp/eval.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid

import numpy as np
import pandas as pd
from sqlalchemy import and_, or_, select

from app.core.database import AsyncSessionLocal
from app.models.pitch_appearance import PitchAppearance
from app.services.alignment import engine as E
import app.models  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("eval_out_model")

GRID = E.GRID
AIR_TRAJECTORIES = ("flyball", "linedrive", "popup")


# ── Engine out-probability surface at the standard alignment ──────────────────

def _standard_out_grids() -> tuple[np.ndarray, np.ndarray]:
    """Return (ground_p_grid, air_p_grid): per-cell P(out) under the standard
    alignment with league-average fielders. Mirrors the trajectory weighting in
    engine._expected_outs exactly (ground → IF cov + 0.15·OF; air → OF cov +
    0.30·IF), reusing engine._combined_coverage rather than reimplementing it."""
    reaches = []
    for pos, (cx, cy) in E.STANDARD_POSITIONS.items():
        if pos in ("C", "P"):
            continue
        # None attributes → engine league-average defaults (27 ft/s, 0.4s, 85%)
        reaches.append(E.compute_reach(uuid.uuid4(), pos, cx, cy, None, None, None))

    infield = [r for r in reaches if r.position in E.INFIELD]
    outfield = [r for r in reaches if r.position in E.OUTFIELD]
    in_cov = E._combined_coverage(infield)
    out_cov = E._combined_coverage(outfield)

    ground_p = np.maximum(in_cov, out_cov * 0.15)
    air_p = np.maximum(out_cov, in_cov * 0.30)
    return ground_p.astype(np.float32), air_p.astype(np.float32)


def _hc_to_cell(hc_x: np.ndarray, hc_y: np.ndarray, season: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Delegates to the canonical era-aware transform (landing.hc_to_cell) so
    the calibrator fit path and serving share one ball frame. NOTE
    (2026-09-04): gained `season` in the frame rebuild — results produced
    before that date used the legacy fixed transform (see EXPERIMENTS.md)."""
    from app.services.alignment.landing import hc_to_cell

    return hc_to_cell(hc_x, hc_y, season)


def engine_p_out(df: pd.DataFrame) -> np.ndarray:
    ground_p, air_p = _standard_out_grids()
    row, col = _hc_to_cell(
        df["hc_x"].to_numpy(float), df["hc_y"].to_numpy(float), df["season"].to_numpy(float)
    )
    is_air = df["ball_trajectory"].isin(AIR_TRAJECTORIES).to_numpy()
    p = np.where(is_air, air_p[row, col], ground_p[row, col])
    return p.astype(float)


# ── Metrics (pure numpy; no sklearn/scipy dependency) ─────────────────────────

def log_loss(y: np.ndarray, p: np.ndarray, eps: float = 1e-6) -> float:
    p = np.clip(p, eps, 1 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _rankdata_avg(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a)
    sorter = np.argsort(a, kind="mergesort")
    inv = np.empty_like(sorter)
    inv[sorter] = np.arange(len(a))
    a_sorted = a[sorter]
    obs = np.r_[True, a_sorted[1:] != a_sorted[:-1]]
    dense = obs.cumsum()[inv]
    count = np.r_[np.nonzero(obs)[0], len(a)]
    return 0.5 * (count[dense] + count[dense - 1] + 1)


def auc(y: np.ndarray, p: np.ndarray) -> float:
    y = np.asarray(y)
    n_pos = int(y.sum())
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    r = _rankdata_avg(p)
    return float((r[y == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def calibration(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> dict:
    """Quantile-binned reliability + a weighted linear fit (slope≈1, intercept≈0
    ⇒ p is a valid probability)."""
    order = np.argsort(p)
    p_s, y_s = p[order], y[order]
    edges = np.linspace(0, len(p), n_bins + 1).astype(int)
    pred_means, obs_rates, weights = [], [], []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        if hi <= lo:
            continue
        pred_means.append(float(p_s[lo:hi].mean()))
        obs_rates.append(float(y_s[lo:hi].mean()))
        weights.append(hi - lo)
    pred_means = np.array(pred_means)
    obs_rates = np.array(obs_rates)
    weights = np.array(weights, dtype=float)
    if len(pred_means) >= 2:
        W = np.diag(weights)
        X = np.c_[np.ones_like(pred_means), pred_means]
        beta = np.linalg.lstsq(W @ X, W @ obs_rates, rcond=None)[0]
        intercept, slope = float(beta[0]), float(beta[1])
    else:
        intercept, slope = float("nan"), float("nan")
    return {
        "slope": slope,
        "intercept": intercept,
        "bins": [
            {"pred": pm, "obs": ob, "n": int(w)}
            for pm, ob, w in zip(pred_means, obs_rates, weights)
        ],
    }


def all_metrics(y: np.ndarray, p: np.ndarray) -> dict:
    return {"log_loss": log_loss(y, p), "brier": brier(y, p), "auc": auc(y, p)}


# ── Baselines (fit on train fold, applied on test fold) ───────────────────────

def fit_baselines(train: pd.DataFrame) -> dict:
    global_rate = float(train["y"].mean())
    zone_rate = train.groupby("fielding_zone")["y"].mean().to_dict()
    train_air = train["ball_trajectory"].isin(AIR_TRAJECTORIES)
    zt_rate = (
        train.assign(_air=train_air)
        .groupby(["fielding_zone", "_air"])["y"]
        .mean()
        .to_dict()
    )
    return {"global": global_rate, "zone": zone_rate, "zone_traj": zt_rate}


def apply_baseline_zone(test: pd.DataFrame, fitted: dict) -> np.ndarray:
    g = fitted["global"]
    return test["fielding_zone"].map(lambda z: fitted["zone"].get(z, g)).to_numpy(float)


def apply_baseline_zone_traj(test: pd.DataFrame, fitted: dict) -> np.ndarray:
    g = fitted["global"]
    air = test["ball_trajectory"].isin(AIR_TRAJECTORIES).to_numpy()
    out = np.empty(len(test))
    for i, (z, a) in enumerate(zip(test["fielding_zone"].to_numpy(), air)):
        out[i] = fitted["zone_traj"].get((z, bool(a)), g)
    return out


# ── Clustered bootstrap (resample games) ──────────────────────────────────────

def bootstrap_ci(
    y: np.ndarray, p_engine: np.ndarray, p_base: np.ndarray,
    game_ids: np.ndarray, B: int, rng: np.random.Generator,
) -> dict:
    """Game-clustered bootstrap CIs for engine−baseline deltas on two axes:
      - log loss  (negative ⇒ engine better calibration+sharpness)
      - AUC       (positive ⇒ engine better discrimination/ranking)
    Resamples whole games to respect within-game correlation."""
    games, inv = np.unique(game_ids, return_inverse=True)
    idx_by_game = [np.where(inv == g)[0] for g in range(len(games))]
    d_ll = np.empty(B)
    d_auc = np.empty(B)
    for b in range(B):
        pick = rng.integers(0, len(games), len(games))
        idx = np.concatenate([idx_by_game[g] for g in pick])
        yy = y[idx]
        d_ll[b] = log_loss(yy, p_engine[idx]) - log_loss(yy, p_base[idx])
        d_auc[b] = auc(yy, p_engine[idx]) - auc(yy, p_base[idx])
    return {
        "log_loss": {"mean": float(d_ll.mean()), "ci95": [float(x) for x in np.percentile(d_ll, [2.5, 97.5])]},
        "auc": {"mean": float(d_auc.mean()), "ci95": [float(x) for x in np.percentile(d_auc, [2.5, 97.5])]},
    }


# ── Data ──────────────────────────────────────────────────────────────────────

async def load_balls(seasons: list[int] | None, alignment_mode: str = "standard") -> pd.DataFrame:
    """In-play batted balls, HR excluded. Filtered by the trajectory-relevant
    fielder alignment:
      - "standard"    → relevant alignment == "Standard" (the P0 population).
      - "nonstandard" → relevant alignment present but != "Standard" (shifted;
                        used only for the position-invariance transfer check).
    Alignment NULL (not backfilled) is excluded either way."""
    is_air = PitchAppearance.ball_trajectory.in_(AIR_TRAJECTORIES)
    is_ground = PitchAppearance.ball_trajectory == "groundball"
    if alignment_mode == "standard":
        align_filter = or_(
            and_(is_ground, PitchAppearance.if_fielding_alignment == "Standard"),
            and_(is_air, PitchAppearance.of_fielding_alignment == "Standard"),
        )
    elif alignment_mode == "nonstandard":
        align_filter = or_(
            and_(is_ground, PitchAppearance.if_fielding_alignment.is_not(None),
                 PitchAppearance.if_fielding_alignment != "Standard"),
            and_(is_air, PitchAppearance.of_fielding_alignment.is_not(None),
                 PitchAppearance.of_fielding_alignment != "Standard"),
        )
    else:
        raise ValueError(f"unknown alignment_mode: {alignment_mode}")
    stmt = select(
        PitchAppearance.season,
        PitchAppearance.game_id,
        PitchAppearance.hc_x,
        PitchAppearance.hc_y,
        PitchAppearance.fielding_zone,
        PitchAppearance.ball_trajectory,
        PitchAppearance.general_result,
    ).where(
        PitchAppearance.general_result.in_(("hit", "out")),
        PitchAppearance.specific_result != "hr",
        PitchAppearance.hc_x.is_not(None),
        PitchAppearance.hc_y.is_not(None),
        PitchAppearance.fielding_zone.is_not(None),
        PitchAppearance.ball_trajectory.is_not(None),
        align_filter,
    )
    if seasons:
        stmt = stmt.where(PitchAppearance.season.in_(seasons))

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(stmt)).mappings().all()
    df = pd.DataFrame(rows)
    if not df.empty:
        df["y"] = (df["general_result"] == "out").astype(int)
    return df


# ── Orchestration (leave-one-season-out) ──────────────────────────────────────

def run_loso(df: pd.DataFrame, bootstrap: int) -> dict:
    rng = np.random.default_rng(42)
    df = df.copy()
    df["p_engine"] = engine_p_out(df)

    seasons = sorted(df["season"].unique())
    # Engine prediction is fold-independent (no fit); pool every ball's held-out
    # prediction into one evaluation, fitting baselines on the other seasons.
    p_zone = np.empty(len(df))
    p_zt = np.empty(len(df))
    p_glob = np.empty(len(df))
    per_season = {}
    for s in seasons:
        test_mask = (df["season"] == s).to_numpy()
        train = df[~test_mask]
        test = df[test_mask]
        fitted = fit_baselines(train)
        pz = apply_baseline_zone(test, fitted)
        pzt = apply_baseline_zone_traj(test, fitted)
        pg = np.full(len(test), fitted["global"])
        p_zone[test_mask] = pz
        p_zt[test_mask] = pzt
        p_glob[test_mask] = pg
        yv = test["y"].to_numpy()
        per_season[int(s)] = {
            "n": int(len(test)),
            "out_rate": float(yv.mean()),
            "engine": all_metrics(yv, test["p_engine"].to_numpy()),
            "baseline_zone": all_metrics(yv, pz),
            "delta_ll_engine_minus_zone": log_loss(yv, test["p_engine"].to_numpy()) - log_loss(yv, pz),
        }

    y = df["y"].to_numpy()
    pe = df["p_engine"].to_numpy()
    pooled = {
        "n": int(len(df)),
        "out_rate": float(y.mean()),
        "engine": all_metrics(y, pe),
        "baseline_global": all_metrics(y, p_glob),
        "baseline_zone": all_metrics(y, p_zone),
        "baseline_zone_traj": all_metrics(y, p_zt),
        "calibration_engine": calibration(y, pe),
    }
    ci = bootstrap_ci(y, pe, p_zone, df["game_id"].to_numpy(), bootstrap, rng)
    pooled["delta_engine_minus_zone"] = ci  # {log_loss:{...}, auc:{...}}

    verdict = _verdict(pooled)
    return {"seasons": [int(s) for s in seasons], "pooled": pooled, "per_season": per_season, "verdict": verdict}


def _verdict(pooled: dict) -> dict:
    """Decision per the pre-registered rule. Discrimination is judged on AUC
    (scale-free ranking), calibration on the reliability slope, and sharpness on
    log loss — three distinct axes that can disagree informatively."""
    d_ll = pooled["delta_engine_minus_zone"]["log_loss"]
    d_auc = pooled["delta_engine_minus_zone"]["auc"]
    slope = pooled["calibration_engine"]["slope"]

    discriminates = d_auc["ci95"][0] > 0            # engine AUC beats zone (CI above 0)
    no_discrimination = d_auc["ci95"][0] <= 0 <= d_auc["ci95"][1]
    ll_better = d_ll["ci95"][1] < 0                 # engine log loss lower (CI below 0)
    calibrated = (not np.isnan(slope)) and 0.8 <= slope <= 1.2

    if discriminates and calibrated and ll_better:
        label = "PASS — beats zone baseline on ranking AND calibration → proceed to P1 (counterfactual eval)"
    elif discriminates and not calibrated:
        label = ("DISCRIMINATES BUT MISCALIBRATED — coverage surface ranks outs better than a zone "
                 "lookup (AUC CI > 0), but its values are NOT probabilities (reliability slope "
                 f"{slope:.2f} ≠ 1; log loss far worse). Recalibrate coverage→P(out) and relabel "
                 "predicted_hit_pct; the geometry has signal and should be recalibrated, not discarded.")
    elif no_discrimination:
        label = "TIE — no ranking gain over an 8-zone lookup; investigate coordinate/coverage before any prescriptive claim"
    else:
        label = "FAIL — worse than a zone lookup on ranking; coverage surface is not trustworthy"
    return {
        "label": label,
        "discriminates": bool(discriminates),
        "calibrated": bool(calibrated),
        "log_loss_better": bool(ll_better),
    }


# ── Reporting ─────────────────────────────────────────────────────────────────

def print_report(res: dict) -> None:
    p = res["pooled"]
    print("\n" + "=" * 74)
    print("P0 EVAL — engine P(out|standard) vs trivial baselines  (LOSO, pooled)")
    print("=" * 74)
    print(f"Seasons: {res['seasons']}   n balls: {p['n']:,}   out rate: {p['out_rate']:.3f}\n")
    hdr = f"{'model':<20}{'log loss':>12}{'brier':>10}{'auc':>10}"
    print(hdr)
    print("-" * len(hdr))
    for name, key in [
        ("engine", "engine"),
        ("baseline_global", "baseline_global"),
        ("baseline_zone (BAR)", "baseline_zone"),
        ("baseline_zone_traj", "baseline_zone_traj"),
    ]:
        m = p[key]
        print(f"{name:<20}{m['log_loss']:>12.5f}{m['brier']:>10.5f}{m['auc']:>10.4f}")
    d_ll = p["delta_engine_minus_zone"]["log_loss"]
    d_auc = p["delta_engine_minus_zone"]["auc"]
    cal = p["calibration_engine"]
    print(f"\nΔ AUC      (engine − zone): {d_auc['mean']:+.4f}  95% CI [{d_auc['ci95'][0]:+.4f}, {d_auc['ci95'][1]:+.4f}]")
    print("  (positive & CI>0 ⇒ engine ranks outs better = real spatial signal)")
    print(f"Δ log loss (engine − zone): {d_ll['mean']:+.5f}  95% CI [{d_ll['ci95'][0]:+.5f}, {d_ll['ci95'][1]:+.5f}]")
    print("  (negative & CI<0 ⇒ engine better calibrated+sharper)")
    print(f"Engine calibration: slope={cal['slope']:.3f}  intercept={cal['intercept']:+.3f}  (want slope≈1, int≈0)")
    print("\nPer-season stability:")
    for s, ps in res["per_season"].items():
        print(f"  {s}: n={ps['n']:>7,}  engine_auc={ps['engine']['auc']:.4f}  "
              f"zone_auc={ps['baseline_zone']['auc']:.4f}  |  "
              f"engine_ll={ps['engine']['log_loss']:.4f}  zone_ll={ps['baseline_zone']['log_loss']:.4f}")
    print("\nVERDICT: " + res["verdict"]["label"])
    print("=" * 74 + "\n")


def save_reliability_plot(res: dict, path: str) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        logger.warning("matplotlib unavailable, skipping plot: %s", exc)
        return
    cal = res["pooled"]["calibration_engine"]
    preds = [b["pred"] for b in cal["bins"]]
    obs = [b["obs"] for b in cal["bins"]]
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "--", color="gray", label="perfect")
    ax.plot(preds, obs, "o-", color="#b5651d", label="engine")
    ax.set_xlabel("predicted P(out)")
    ax.set_ylabel("observed out rate")
    ax.set_title(f"Engine reliability (slope={cal['slope']:.2f})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    logger.info("Reliability plot → %s", path)


async def main(seasons, bootstrap, out_json, out_plot) -> None:
    df = await load_balls(seasons)
    if df.empty:
        logger.warning(
            "No standard-alignment batted balls found. Has alignment been "
            "backfilled? (scripts/backfill_alignment.py). Exiting."
        )
        return
    logger.info("Loaded %d standard-alignment batted balls across seasons %s",
                len(df), sorted(df["season"].unique()))
    res = run_loso(df, bootstrap)
    print_report(res)
    if out_json:
        def _np(o):
            if isinstance(o, (np.integer,)):
                return int(o)
            if isinstance(o, (np.floating,)):
                return float(o)
            raise TypeError(f"not serializable: {type(o)}")
        with open(out_json, "w") as f:
            json.dump(res, f, indent=2, default=_np)
        logger.info("Results JSON → %s", out_json)
    if out_plot:
        save_reliability_plot(res, out_plot)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=int, nargs="+", help="Seasons to include (default: all backfilled)")
    parser.add_argument("--bootstrap", type=int, default=500, help="Bootstrap resamples for the CI")
    parser.add_argument("--out-json", type=str, default="/tmp/p0_eval.json")
    parser.add_argument("--out-plot", type=str, default="/tmp/p0_reliability.png")
    args = parser.parse_args()
    asyncio.run(main(args.seasons, args.bootstrap, args.out_json, args.out_plot))
