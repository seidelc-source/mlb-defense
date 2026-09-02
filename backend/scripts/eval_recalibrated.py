"""
Recalibration experiment — turn the engine's `coverage` into a calibrated
P(out) and test whether the (already rank-superior) coverage geometry beats the
zone lookup as a PROBABILITY once both are calibrated.

See documentation/EXPERIMENTS.md (2026-09-02 entry) for the pre-registration:
method = isotonic + logistic (compared); granularity = per-trajectory (ground/
air); scope = offline eval-only (no engine/API change). Recalibration is
monotonic ⇒ AUC is preserved; the open question is log loss / Brier / slope.

READ-ONLY: no engine, model, or DB changes. Calibrators are fit OUT-OF-FOLD
(train seasons only) under the same LOSO structure as the P0 harness.

Usage:
    cd backend
    python -m scripts.eval_recalibrated --seasons 2016 2017 2018 2019 2020 2021 2022 2023 2024 2025 \
        --bootstrap 300 --out-json /tmp/recal_eval.json --out-plot-prefix /tmp/recal
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from scripts.eval_out_model import (
    AIR_TRAJECTORIES,
    all_metrics,
    apply_baseline_zone,
    apply_baseline_zone_traj,
    auc,
    bootstrap_ci,
    brier,
    calibration,
    engine_p_out,
    fit_baselines,
    load_balls,
    log_loss,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("eval_recalibrated")

_EPS = 1e-4


def _air_mask(traj: pd.Series | np.ndarray) -> np.ndarray:
    return pd.Series(traj).isin(AIR_TRAJECTORIES).to_numpy()


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, _EPS, 1 - _EPS)
    return np.log(p / (1 - p))


# ── Per-trajectory calibrators ────────────────────────────────────────────────

def _fit_one(method: str, p_raw: np.ndarray, y: np.ndarray):
    if method == "isotonic":
        m = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        m.fit(p_raw, y)
        return ("isotonic", m)
    if method == "logistic":
        m = LogisticRegression(solver="lbfgs")
        m.fit(_logit(p_raw).reshape(-1, 1), y)
        return ("logistic", m)
    raise ValueError(method)


def _predict_one(fitted, p_raw: np.ndarray) -> np.ndarray:
    kind, m = fitted
    if kind == "isotonic":
        return np.clip(m.predict(p_raw), 0.0, 1.0)
    return m.predict_proba(_logit(p_raw).reshape(-1, 1))[:, 1]


def fit_calibrators(method: str, train: pd.DataFrame) -> dict:
    """One calibrator per trajectory class (ground / air)."""
    air = _air_mask(train["ball_trajectory"])
    cals = {}
    for name, mask in (("ground", ~air), ("air", air)):
        cals[name] = _fit_one(method, train.loc[mask, "p_raw"].to_numpy(),
                               train.loc[mask, "y"].to_numpy())
    return cals


def apply_calibrators(cals: dict, test: pd.DataFrame) -> np.ndarray:
    air = _air_mask(test["ball_trajectory"])
    out = np.empty(len(test))
    for name, mask in (("ground", ~air), ("air", air)):
        if mask.any():
            out[mask] = _predict_one(cals[name], test.loc[mask, "p_raw"].to_numpy())
    return out


# ── LOSO recalibration ────────────────────────────────────────────────────────

def run(df: pd.DataFrame, bootstrap: int) -> dict:
    rng = np.random.default_rng(42)
    df = df.copy()
    df["p_raw"] = engine_p_out(df)

    seasons = sorted(int(s) for s in df["season"].unique())
    n = len(df)
    p_iso = np.empty(n)
    p_log = np.empty(n)
    p_zone = np.empty(n)
    p_zt = np.empty(n)

    for s in seasons:
        test_mask = (df["season"] == s).to_numpy()
        train, test = df[~test_mask], df[test_mask]
        # Calibrators fit ONLY on training seasons (out-of-fold).
        iso = fit_calibrators("isotonic", train)
        log = fit_calibrators("logistic", train)
        p_iso[test_mask] = apply_calibrators(iso, test)
        p_log[test_mask] = apply_calibrators(log, test)
        # Baselines fit on the same training folds.
        fitted = fit_baselines(train)
        p_zone[test_mask] = apply_baseline_zone(test, fitted)
        p_zt[test_mask] = apply_baseline_zone_traj(test, fitted)

    y = df["y"].to_numpy()
    p_raw = df["p_raw"].to_numpy()
    games = df["game_id"].to_numpy()

    models = {
        "engine_raw": p_raw,
        "engine_isotonic": p_iso,
        "engine_logistic": p_log,
        "baseline_zone": p_zone,
        "baseline_zone_traj": p_zt,
    }
    pooled = {
        "n": n,
        "out_rate": float(y.mean()),
        "metrics": {k: all_metrics(y, p) for k, p in models.items()},
        "calibration": {
            "engine_raw": calibration(y, p_raw),
            "engine_isotonic": calibration(y, p_iso),
            "engine_logistic": calibration(y, p_log),
        },
    }
    # Δ vs the pre-registered bar (baseline_zone) for both calibrated variants.
    pooled["delta_vs_zone"] = {
        "isotonic": bootstrap_ci(y, p_iso, p_zone, games, bootstrap, rng),
        "logistic": bootstrap_ci(y, p_log, p_zone, games, bootstrap, rng),
    }
    # Guardrail: vs the stronger zone_traj bar.
    pooled["delta_vs_zone_traj"] = {
        "isotonic": bootstrap_ci(y, p_iso, p_zt, games, bootstrap, rng),
    }

    verdict = _verdict(pooled)
    return {"seasons": seasons, "pooled": pooled, "verdict": verdict}


def _verdict(pooled: dict) -> dict:
    """Pre-registered rule, judged on the ISOTONIC calibrator vs baseline_zone."""
    d = pooled["delta_vs_zone"]["isotonic"]["log_loss"]
    slope = pooled["calibration"]["engine_isotonic"]["slope"]
    beats_ll = d["ci95"][1] < 0
    ties_ll = d["ci95"][0] <= 0 <= d["ci95"][1]
    calibrated = (not np.isnan(slope)) and 0.9 <= slope <= 1.1
    if beats_ll and calibrated:
        label = ("PASS — calibrated coverage beats the zone lookup on log loss (CI<0) and is "
                 "well-calibrated (slope≈1). The continuous geometry is a valid probability model "
                 "→ relabel/wire predicted_hit_pct (separate decision) and unblock P1.")
    elif ties_ll and calibrated:
        label = ("TIE — recalibration fixes the numbers (slope≈1) but calibrated coverage only "
                 "matches the 8-zone lookup on log loss; the finer resolution doesn't pay off as a "
                 "probability. Reconsider before investing in the range model.")
    else:
        label = ("FAIL — recalibration insufficient (slope off or still worse than zone). The "
                 "problem is the coverage model's shape, not just its scale → revisit compute_reach.")
    return {"label": label, "beats_zone_ll": bool(beats_ll), "ties_zone_ll": bool(ties_ll),
            "isotonic_calibrated": bool(calibrated)}


# ── Position-invariance transfer check (bonus) ────────────────────────────────

def transfer_check(df_std: pd.DataFrame, df_shift: pd.DataFrame) -> dict:
    """Fit per-trajectory isotonic calibrators on ALL standard-alignment balls,
    apply to shifted-alignment balls, and report calibration there.

    CAVEAT (honest framing): we lack the actual shifted fielder coordinates, so
    coverage is still computed at STANDARD positions. This is therefore a
    TRANSFER/robustness check (does the standard-fit coverage→out map hold on a
    differently-selected, differently-fielded population?), NOT a pure
    position-invariance test. A large calibration miss here is still a red flag
    for the prescriptive layer; a clean fit is reassuring but not conclusive."""
    std = df_std.copy()
    std["p_raw"] = engine_p_out(std)
    shift = df_shift.copy()
    shift["p_raw"] = engine_p_out(shift)

    cals = fit_calibrators("isotonic", std)  # fit on standard
    y_sh = shift["y"].to_numpy()
    p_sh = apply_calibrators(cals, shift)
    # Reference: same calibrator re-applied to standard (in-population).
    p_st = apply_calibrators(cals, std)
    y_st = std["y"].to_numpy()
    return {
        "n_shift": int(len(shift)),
        "shift_out_rate": float(y_sh.mean()),
        "std_out_rate": float(y_st.mean()),
        "on_shift": {**all_metrics(y_sh, p_sh), "calibration": calibration(y_sh, p_sh)},
        "on_standard_ref": {**all_metrics(y_st, p_st), "calibration": calibration(y_st, p_st)},
    }


# ── Reporting ─────────────────────────────────────────────────────────────────

def print_report(res: dict, transfer: dict | None) -> None:
    p = res["pooled"]
    print("\n" + "=" * 78)
    print("RECALIBRATION — calibrated engine coverage vs zone baseline  (LOSO, pooled)")
    print("=" * 78)
    print(f"Seasons: {res['seasons']}   n balls: {p['n']:,}   out rate: {p['out_rate']:.3f}\n")
    hdr = f"{'model':<24}{'log loss':>12}{'brier':>10}{'auc':>10}{'cal slope':>11}"
    print(hdr); print("-" * len(hdr))
    cal = p["calibration"]
    for name in ["engine_raw", "engine_isotonic", "engine_logistic", "baseline_zone", "baseline_zone_traj"]:
        m = p["metrics"][name]
        slope = cal.get(name, {}).get("slope", float("nan"))
        slope_s = f"{slope:>11.3f}" if not np.isnan(slope) else f"{'—':>11}"
        print(f"{name:<24}{m['log_loss']:>12.5f}{m['brier']:>10.5f}{m['auc']:>10.4f}{slope_s}")
    for bar, key in [("baseline_zone", "delta_vs_zone"), ("baseline_zone_traj", "delta_vs_zone_traj")]:
        for method, d in p[key].items():
            ll = d["log_loss"]
            print(f"\nΔ log loss ({method} − {bar}): {ll['mean']:+.5f}  95% CI [{ll['ci95'][0]:+.5f}, {ll['ci95'][1]:+.5f}]")
    print("\nVERDICT: " + res["verdict"]["label"])
    if transfer:
        t = transfer
        print("\n" + "-" * 78)
        print("BONUS — transfer check (std-fit isotonic applied to SHIFTED-alignment balls)")
        print(f"  n shifted: {t['n_shift']:,}   shift out rate: {t['shift_out_rate']:.3f}   std out rate: {t['std_out_rate']:.3f}")
        print(f"  on shifted:  log loss {t['on_shift']['log_loss']:.5f}  slope {t['on_shift']['calibration']['slope']:.3f}")
        print(f"  on standard: log loss {t['on_standard_ref']['log_loss']:.5f}  slope {t['on_standard_ref']['calibration']['slope']:.3f}")
        print("  (caveat: coverage computed at STANDARD positions — transfer/robustness, not pure position-invariance)")
    print("=" * 78 + "\n")


def save_plots(res: dict, prefix: str) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        logger.warning("matplotlib unavailable, skipping plots: %s", exc)
        return
    cal = res["pooled"]["calibration"]
    fig, ax = plt.subplots(figsize=(5.2, 5.2))
    ax.plot([0, 1], [0, 1], "--", color="gray", label="perfect")
    for name, color in [("engine_raw", "#b5651d"), ("engine_isotonic", "#2a7f62"), ("engine_logistic", "#3a6ea5")]:
        bins = cal[name]["bins"]
        ax.plot([b["pred"] for b in bins], [b["obs"] for b in bins], "o-", color=color,
                label=f"{name.replace('engine_','')} (slope {cal[name]['slope']:.2f})")
    ax.set_xlabel("predicted P(out)"); ax.set_ylabel("observed out rate")
    ax.set_title("Reliability: raw vs recalibrated coverage")
    ax.legend(); fig.tight_layout()
    path = f"{prefix}_reliability.png"
    fig.savefig(path, dpi=110)
    logger.info("Reliability plot → %s", path)


async def main(seasons, bootstrap, out_json, out_plot_prefix, skip_transfer) -> None:
    df = await load_balls(seasons, alignment_mode="standard")
    if df.empty:
        logger.warning("No standard-alignment balls found — backfill alignment first. Exiting.")
        return
    logger.info("Loaded %d standard-alignment balls, seasons %s", len(df), sorted(df["season"].unique()))
    res = run(df, bootstrap)

    transfer = None
    if not skip_transfer:
        df_shift = await load_balls(seasons, alignment_mode="nonstandard")
        if not df_shift.empty:
            logger.info("Loaded %d shifted-alignment balls for transfer check", len(df_shift))
            transfer = transfer_check(df, df_shift)
            res["transfer_check"] = transfer

    print_report(res, transfer)
    if out_json:
        def _np(o):
            if isinstance(o, np.integer):
                return int(o)
            if isinstance(o, np.floating):
                return float(o)
            raise TypeError(f"not serializable: {type(o)}")
        with open(out_json, "w") as f:
            json.dump(res, f, indent=2, default=_np)
        logger.info("Results JSON → %s", out_json)
    if out_plot_prefix:
        save_plots(res, out_plot_prefix)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=int, nargs="+")
    parser.add_argument("--bootstrap", type=int, default=300)
    parser.add_argument("--out-json", type=str, default="/tmp/recal_eval.json")
    parser.add_argument("--out-plot-prefix", type=str, default="/tmp/recal")
    parser.add_argument("--skip-transfer", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.seasons, args.bootstrap, args.out_json, args.out_plot_prefix, args.skip_transfer))
