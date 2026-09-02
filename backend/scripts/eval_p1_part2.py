"""
P1 — Part 2: off-policy value of the infield-shift DECISION.

Question: does a shift *policy* (which batters to shift) convert more outs than
trivial policies — always-standard, always-shift, actual MLB — and how much of
the oracle gap does the engine's pull-based shift-selection capture?

See documentation/EXPERIMENTS.md (P1 pre-registration). DEVIATION from the
pre-registered doubly-robust/IPW plan (documented): because we observe BOTH arms
(Standard and Infield shift) per batter, we use a cleaner WITHIN-BATTER
policy-value estimator — credit each batter their realized out-rate under the
arm the policy picks, weighted by their ball volume. This needs no propensity
model, and it uses REALIZED arm outcomes (not the engine's coverage model), so
there is no circularity. Scope unchanged: categorical infield shift on GROUND
balls, 2016–2022. Quasi-experimental — residual confounding remains (see below).

READ-ONLY: no engine/DB changes.

Usage:
    cd backend
    python -m scripts.eval_p1_part2 --min-per-arm 40 --bootstrap 1000 \
        --out-json /tmp/p1_part2.json --out-plot /tmp/p1_part2_curve.png
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging

import numpy as np
import pandas as pd

from scripts.eval_p1_part1 import GRID, load_ground_balls

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("eval_p1_part2")


# ── Per-batter arm outcomes + shiftability ────────────────────────────────────

def _batter_row(sub: pd.DataFrame) -> dict | None:
    """Hand-adjusted out rate under each arm (Standard vs Infield shift), plus
    pull-concentration (handedness-agnostic shiftability). Arm rates are
    precision-weighted across pitcher-hand strata that have both arms present, to
    curb the hand-mix confound (a defense may shift more vs same-handed pitchers).
    Returns None if no stratum has both arms."""
    num_std = num_shf = wsum = 0.0
    n_std = n_shift = out_std = out_shift = 0
    for _, g in sub.groupby("pitcher_hand"):
        std = g[g["is_shift"] == 0]
        shf = g[g["is_shift"] == 1]
        ns, nf = len(std), len(shf)
        n_std += ns
        n_shift += nf
        out_std += int(std["y"].sum())
        out_shift += int(shf["y"].sum())
        if ns == 0 or nf == 0:
            continue
        w = ns + nf
        num_std += w * (std["y"].sum() / ns)
        num_shf += w * (shf["y"].sum() / nf)
        wsum += w
    if wsum == 0:
        return None
    # Pull concentration: fraction of grounders on the batter's more-populated
    # side of second base (handedness-agnostic shiftability; nx = col/(GRID-1)).
    nx = sub["col"].to_numpy() / (GRID - 1)
    right = float(np.mean(nx > 0.5))
    concentration = max(right, 1.0 - right)
    return {
        "batter_id": str(sub["batter_id"].iloc[0]),
        "bats": sub["bats"].iloc[0] or "?",
        "n_std": int(n_std),
        "n_shift": int(n_shift),
        "weight": int(n_std + n_shift),
        "rate_std": num_std / wsum,          # hand-adjusted
        "rate_shift": num_shf / wsum,        # hand-adjusted
        "out_std": out_std, "out_shift": out_shift,  # raw counts for "actual"
        "concentration": concentration,
    }


def per_batter_table(df: pd.DataFrame, min_per_arm: int) -> pd.DataFrame:
    recs = []
    for _, sub in df.groupby("batter_id"):
        if int((sub["is_shift"] == 0).sum()) < min_per_arm or int((sub["is_shift"] == 1).sum()) < min_per_arm:
            continue
        r = _batter_row(sub)
        if r is not None:
            recs.append(r)
    return pd.DataFrame(recs)


# ── Policy values (within-batter direct estimate) ─────────────────────────────

def _policy_rate_per_batter(tbl: pd.DataFrame, decision: np.ndarray) -> np.ndarray:
    """Per-batter out rate under a policy: shift arm where decision is True."""
    return np.where(decision, tbl["rate_shift"].to_numpy(), tbl["rate_std"].to_numpy())


def _weighted(values: np.ndarray, weights: np.ndarray) -> float:
    return float(np.sum(values * weights) / np.sum(weights))


def policy_values(tbl: pd.DataFrame, threshold: float) -> dict:
    w = tbl["weight"].to_numpy(float)
    rate_std = tbl["rate_std"].to_numpy()
    rate_shift = tbl["rate_shift"].to_numpy()
    conc = tbl["concentration"].to_numpy()

    v_standard = _weighted(rate_std, w)
    v_shift = _weighted(rate_shift, w)
    v_oracle = _weighted(np.maximum(rate_std, rate_shift), w)
    v_worst = _weighted(np.minimum(rate_std, rate_shift), w)
    v_policy = _weighted(_policy_rate_per_batter(tbl, conc >= threshold), w)
    # "Actual" = realized out rate under the mix MLB actually used.
    v_actual = float((tbl["out_std"].sum() + tbl["out_shift"].sum()) /
                     (tbl["n_std"].sum() + tbl["n_shift"].sum()))
    shift_frac = float(np.sum(w[conc >= threshold]) / np.sum(w))
    return {
        "v_standard": v_standard, "v_shift": v_shift, "v_oracle": v_oracle,
        "v_worst": v_worst, "v_policy": v_policy, "v_actual": v_actual,
        "policy_shift_fraction": shift_frac,
        # fraction of the oracle-over-standard gap the policy captures
        "oracle_gap_captured": (
            (v_policy - v_standard) / (v_oracle - v_standard)
            if v_oracle > v_standard else float("nan")
        ),
    }


def sweep_threshold(tbl: pd.DataFrame, taus: np.ndarray) -> list[dict]:
    out = []
    w = tbl["weight"].to_numpy(float)
    conc = tbl["concentration"].to_numpy()
    for t in taus:
        v = _weighted(_policy_rate_per_batter(tbl, conc >= t), w)
        out.append({"tau": float(t), "v_policy": v,
                    "shift_fraction": float(np.sum(w[conc >= t]) / np.sum(w))})
    return out


def bootstrap_deltas(tbl: pd.DataFrame, threshold: float, B: int, rng) -> dict:
    """Bootstrap over batters: CIs for policy − standard, shift − standard,
    oracle − standard (all in out-rate points)."""
    n = len(tbl)
    d_policy = np.empty(B); d_shift = np.empty(B); d_oracle = np.empty(B)
    idx_all = np.arange(n)
    for b in range(B):
        idx = rng.integers(0, n, n)
        s = tbl.iloc[idx]
        pv = policy_values(s, threshold)
        d_policy[b] = pv["v_policy"] - pv["v_standard"]
        d_shift[b] = pv["v_shift"] - pv["v_standard"]
        d_oracle[b] = pv["v_oracle"] - pv["v_standard"]
    def ci(a):
        return {"mean": float(a.mean()), "ci95": [float(x) for x in np.percentile(a, [2.5, 97.5])]}
    return {"policy_minus_standard": ci(d_policy),
            "shift_minus_standard": ci(d_shift),
            "oracle_minus_standard": ci(d_oracle)}


# ── Verdict ───────────────────────────────────────────────────────────────────

def _verdict(pv: dict, boot: dict, sweep: list[dict]) -> dict:
    ds = boot["shift_minus_standard"]
    shift_beats_standard = ds["ci95"][0] > 0
    # Does ANY selective policy (shifting <90% of volume) beat always-shift?
    selective = [r for r in sweep if r["shift_fraction"] < 0.90]
    best_sel = max(selective, key=lambda r: r["v_policy"]) if selective else None
    selection_beats_broad = bool(best_sel and best_sel["v_policy"] > pv["v_shift"] + 0.002)
    # Is V(τ) monotone decreasing in selectivity (more shifting → more outs)?
    vs = [r["v_policy"] for r in sorted(sweep, key=lambda r: r["shift_fraction"])]  # low→high shift frac
    monotone_more_shift_better = vs[-1] >= max(vs) - 1e-9

    parts = []
    if shift_beats_standard:
        parts.append(
            f"Shifting broadly converts MORE outs than always-standard "
            f"(+{ds['mean']*1000:.1f}/1000 balls, CI [{ds['ci95'][0]*1000:+.1f},{ds['ci95'][1]*1000:+.1f}]).")
    else:
        parts.append("Broad shifting does not beat always-standard.")
    if not selection_beats_broad:
        parts.append(
            "But the pull-concentration SELECTION does NOT beat shifting everyone — V(τ) declines "
            "monotonically as fewer (more-concentrated) batters are shifted, so the most-pull batters "
            "are NOT disproportionately the ones who benefit. The engine's pull-based shift-selection "
            "adds no value over a trivial 'shift everyone' policy on this data.")
    else:
        parts.append(f"A selective policy (shift {best_sel['shift_fraction']*100:.0f}%) beats always-shift.")
    parts.append(
        f"Perfect selection (oracle) would add "
        f"+{boot['oracle_minus_standard']['mean']*1000:.1f}/1000 vs standard "
        f"({(pv['v_oracle']-pv['v_shift'])*1000:+.1f}/1000 beyond broad shifting) — so selection value "
        f"EXISTS but pull-concentration is not the signal that captures it.")
    return {
        "label": " ".join(parts),
        "shift_beats_standard": shift_beats_standard,
        "selection_beats_broad_shifting": selection_beats_broad,
        "more_shifting_monotonically_better": bool(monotone_more_shift_better),
    }


# ── Reporting ─────────────────────────────────────────────────────────────────

def print_report(res: dict) -> None:
    pv = res["policy_values"]; boot = res["bootstrap"]
    print("\n" + "=" * 80)
    print("P1 · PART 2 — off-policy value of the infield-shift DECISION (within-batter)")
    print("=" * 80)
    print(f"Ground balls 2016–2022; {res['n_batters']} batters (≥{res['min_per_arm']}/arm). "
          f"Policy threshold τ={res['threshold']:.2f} on pull-concentration "
          f"(shifts {pv['policy_shift_fraction']*100:.0f}% of ball volume).\n")
    print("  Policy out-rates (higher = more outs converted):")
    for name, key in [("always-standard", "v_standard"), ("always-shift", "v_shift"),
                      ("actual (MLB mix)", "v_actual"), ("pull-concentration policy", "v_policy"),
                      ("ORACLE (shift iff it helps)", "v_oracle"),
                      ("worst (anti-oracle)", "v_worst")]:
        print(f"    {name:<28} {pv[key]:.4f}")
    print("\n  Deltas vs always-standard (out-rate points; ×1000 = outs per 1000 balls):")
    for name, key in [("pull-concentration policy", "policy_minus_standard"),
                      ("always-shift", "shift_minus_standard"),
                      ("oracle", "oracle_minus_standard")]:
        d = boot[key]
        print(f"    {name:<28} {d['mean']*1000:+6.2f}  95% CI [{d['ci95'][0]*1000:+.2f}, {d['ci95'][1]*1000:+.2f}]")
    print(f"\n  Oracle gap captured by the policy: {pv['oracle_gap_captured']*100:.0f}%")
    best = max(res["threshold_sweep"], key=lambda r: r["v_policy"])
    print(f"  Best threshold in sweep: τ={best['tau']:.2f} → V={best['v_policy']:.4f} "
          f"(shifts {best['shift_fraction']*100:.0f}%)")
    print("\nVERDICT: " + res["verdict"]["label"])
    print("=" * 80 + "\n")


def save_curve(res: dict, path: str) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        logger.warning("matplotlib unavailable: %s", exc)
        return
    sw = res["threshold_sweep"]; pv = res["policy_values"]
    taus = [r["tau"] for r in sw]; vs = [r["v_policy"] for r in sw]
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    ax.plot(taus, vs, "-", color="#b5651d", label="pull-concentration policy V(τ)")
    ax.axhline(pv["v_standard"], ls="--", color="gray", label="always-standard")
    ax.axhline(pv["v_shift"], ls=":", color="#3a6ea5", label="always-shift")
    ax.axhline(pv["v_oracle"], ls="-.", color="#2a7f62", label="oracle")
    ax.axvline(res["threshold"], color="k", lw=0.6)
    ax.set_xlabel("shift threshold τ (pull-concentration)")
    ax.set_ylabel("out rate (policy value)")
    ax.set_title("P1 Part 2 — shift-policy value vs threshold")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(path, dpi=110)
    logger.info("Curve → %s", path)


async def main(min_per_arm, threshold, bootstrap, out_json, out_plot) -> None:
    rng = np.random.default_rng(42)
    df = await load_ground_balls()
    logger.info("Loaded %d ground balls (2016–2022, Standard/Infield shift)", len(df))
    tbl = per_batter_table(df, min_per_arm)
    if tbl.empty:
        logger.warning("No qualifying batters at min_per_arm=%d.", min_per_arm)
        return
    logger.info("Qualifying batters: %d", len(tbl))

    pv = policy_values(tbl, threshold)
    boot = bootstrap_deltas(tbl, threshold, bootstrap, rng)
    sweep = sweep_threshold(tbl, np.round(np.arange(0.40, 0.96, 0.05), 2))
    res = {
        "n_batters": int(len(tbl)), "min_per_arm": min_per_arm, "threshold": threshold,
        "by_hand": tbl["bats"].value_counts().to_dict(),
        "policy_values": pv, "bootstrap": boot, "threshold_sweep": sweep,
    }
    res["verdict"] = _verdict(pv, boot, sweep)
    print_report(res)

    if out_json:
        def _np(o):
            if isinstance(o, np.integer):
                return int(o)
            if isinstance(o, np.floating):
                return float(o)
            raise TypeError(str(type(o)))
        with open(out_json, "w") as f:
            json.dump({"summary": res, "batters": tbl.to_dict(orient="records")}, f, indent=2, default=_np)
        logger.info("Results JSON → %s", out_json)
    if out_plot:
        save_curve(res, out_plot)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-per-arm", type=int, default=40)
    parser.add_argument("--threshold", type=float, default=0.60,
                        help="Pull-concentration threshold for the shift decision")
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--out-json", type=str, default="/tmp/p1_part2.json")
    parser.add_argument("--out-plot", type=str, default="/tmp/p1_part2_curve.png")
    args = parser.parse_args()
    asyncio.run(main(args.min_per_arm, args.threshold, args.bootstrap, args.out_json, args.out_plot))
