"""
P1 — Part 1: simulator validation (prescriptive, categorical infield shift).

Question: does the engine's PREDICTED benefit of an infield shift (calibrated
out-model, standard-template vs shift-template) agree with the REALIZED out-rate
benefit of shifting, measured per batter from real outcomes?

See documentation/EXPERIMENTS.md (2026-09-02 P1 pre-registration). Scope:
categorical infield shift on GROUND balls only (infield shift is a ground-ball
phenomenon); 2016–2022 shift era. This validates the engine as an alignment-
ranking simulator on the one axis where alignment truly varies. It does NOT
validate fine x,y placement (unobservable — data gap).

Design notes honored here:
  - Ground truth = realized lift per batter, pitcher-hand-stratified contrast
    (Infield shift − Standard), quasi-experimental (confounders remain — see
    the pre-registration threats).
  - Predicted lift = calibrated ground out-model evaluated at the standard vs
    shift TEMPLATE positions over the batter's own ground-ball locations
    (locations, not outcomes → no outcome leakage on the predicted side).
  - Handedness diagnostic: the engine's infield_shift template shades toward 1B
    (RF side = a LEFT-handed batter's pull). It is handedness-NAIVE. We report
    the engine as-built AND a handedness-corrected variant (shift mirrored for
    right-handed batters) to separate "engine bug" from "model invalid".

READ-ONLY: no engine/DB changes.

Usage:
    cd backend
    python -m scripts.eval_p1_part1 --min-per-arm 40 --bootstrap 1000 \
        --out-json /tmp/p1_part1.json --out-plot /tmp/p1_part1_scatter.png
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
from app.services.alignment import engine as E
from scripts.eval_out_model import _hc_to_cell
import app.models  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("eval_p1_part1")

GRID = E.GRID
SHIFT_ERA = list(range(2016, 2023))  # 2016–2022


# ── Engine ground out-probability grid at a given infield template ────────────

def _ground_out_grid(infield_positions: dict[str, tuple[float, float]]) -> np.ndarray:
    """Per-cell RAW coverage for ground balls: infielders at `infield_positions`,
    outfielders at standard (cross term 0.15) — mirrors eval_out_model's ground
    component so the ground calibrator (fit at standard) applies consistently."""
    inf = [E.compute_reach(_uuid(), p, x, y, None, None, None) for p, (x, y) in infield_positions.items()]
    outf = [E.compute_reach(_uuid(), p, *E.STANDARD_POSITIONS[p], None, None, None) for p in E.OUTFIELD]
    in_cov = E._combined_coverage(inf)
    out_cov = E._combined_coverage(outf)
    return np.maximum(in_cov, out_cov * 0.15).astype(np.float32)


def _uuid():
    import uuid
    return uuid.uuid4()


def _infield_from_engine(shift_type: str, bats: str | None) -> dict[str, tuple[float, float]]:
    """Infield subset of the SHIPPED engine template — so this harness validates
    the real `default_positions_for_shift` (incl. the handedness fix), not a
    private reimplementation."""
    pos = E.default_positions_for_shift(shift_type, bats)
    return {p: pos[p] for p in E.INFIELD}


# ── Data ──────────────────────────────────────────────────────────────────────

async def load_ground_balls() -> pd.DataFrame:
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


# ── Calibrated grids ──────────────────────────────────────────────────────────

def build_calibrated_grids(df_std: pd.DataFrame) -> dict[str, np.ndarray]:
    """Fit the ground isotonic calibrator on STANDARD-alignment ground balls
    (coverage_at_standard → out), then produce calibrated P(out) grids from the
    SHIPPED engine templates: standard, canonical/LH shift, and RH shift (the
    engine's own handedness mirror)."""
    cov_std_grid = _ground_out_grid(_infield_from_engine("standard", None))
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(cov_std_grid[df_std["row"].to_numpy(), df_std["col"].to_numpy()], df_std["y"].to_numpy())

    def cal(grid: np.ndarray) -> np.ndarray:
        return iso.predict(grid.ravel()).reshape(GRID, GRID)

    return {
        "std": cal(cov_std_grid),
        "shift_canonical": cal(_ground_out_grid(_infield_from_engine("infield_shift", "L"))),
        "shift_mirror": cal(_ground_out_grid(_infield_from_engine("infield_shift", "R"))),
        "iso": iso,  # exposed so per-batter optimized grids can be calibrated
        "_iso_slope_check": iso.predict(np.array([0.0, 0.5, 1.0])),
    }


# ── Per-batter optimized shift (the engine's actual curation) ─────────────────

def _grounder_density(sub: pd.DataFrame) -> np.ndarray:
    """Smoothed density of THIS batter's ground-ball locations — the surface the
    engine's optimizer covers. Built from real grounders (locations, not
    outcomes → no outcome leakage)."""
    g = np.zeros((GRID, GRID), dtype=np.float32)
    np.add.at(g, (sub["row"].to_numpy(), sub["col"].to_numpy()), 1.0)
    try:
        from scipy.ndimage import gaussian_filter
        g = gaussian_filter(g, sigma=2.5)
    except Exception:  # noqa: BLE001 — numpy fallback (separable box blur)
        k = np.ones(5, dtype=np.float32) / 5.0
        for ax in (0, 1):
            g = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), ax, g)
    s = g.sum()
    return (g / s).astype(np.float32) if s > 0 else g


def _optimize_infield(density: np.ndarray) -> dict[str, tuple[float, float]]:
    """Run the SHIPPED engine local search (`optimize_positions`) to place the
    four infielders against this batter's grounder density, legal-constrained,
    starting from standard. Outfield is excluded so only infield/ground is
    optimized. Returns the optimized infield positions."""
    inf_pos = {p: E.STANDARD_POSITIONS[p] for p in E.INFIELD}
    reaches = {p: E.compute_reach(_uuid(), p, x, y, None, None, None) for p, (x, y) in inf_pos.items()}
    air0 = np.zeros((GRID, GRID), dtype=np.float32)
    opt = E.optimize_positions(inf_pos, reaches, density, air0, "balanced")
    return {p: opt[p] for p in E.INFIELD}


def predicted_lift_optimized(sub: pd.DataFrame, grids: dict) -> float:
    """Engine's per-batter OPTIMIZED shift benefit: calibrated P(out) under the
    optimized infield minus under standard, over the batter's grounders."""
    opt_inf = _optimize_infield(_grounder_density(sub))
    cov_opt = _ground_out_grid(opt_inf)
    cal_opt = grids["iso"].predict(cov_opt.ravel()).reshape(GRID, GRID)
    rows, cols = sub["row"].to_numpy(), sub["col"].to_numpy()
    return float(cal_opt[rows, cols].mean() - grids["std"][rows, cols].mean())


# ── Per-batter realized & predicted lift ──────────────────────────────────────

def _rate_se(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    return p, (p * (1 - p) / n) ** 0.5


def realized_lift(sub: pd.DataFrame) -> tuple[float, float]:
    """Pitcher-hand-stratified out-rate difference (shift − standard),
    precision-weighted across L/R strata; SE via binomial propagation."""
    num, den, var = 0.0, 0.0, 0.0
    for _, g in sub.groupby("pitcher_hand"):
        std = g[g["is_shift"] == 0]
        shf = g[g["is_shift"] == 1]
        n_std, n_shf = len(std), len(shf)
        if n_std == 0 or n_shf == 0:
            continue
        p_std, se_std = _rate_se(int(std["y"].sum()), n_std)
        p_shf, se_shf = _rate_se(int(shf["y"].sum()), n_shf)
        w = (n_std * n_shf) / (n_std + n_shf)  # precision weight
        num += w * (p_shf - p_std)
        den += w
        var += (w ** 2) * (se_std ** 2 + se_shf ** 2)
    if den == 0:
        return float("nan"), float("nan")
    return num / den, (var ** 0.5) / den


def predicted_lift(sub: pd.DataFrame, grids: dict, bats: str, fixed: bool) -> float:
    """`fixed=True` = shipped engine after the handedness fix (mirror shift for RH
    batters). `fixed=False` = pre-fix engine (always canonical/LH shift)."""
    rows, cols = sub["row"].to_numpy(), sub["col"].to_numpy()
    p_std = grids["std"][rows, cols].mean()
    shift_key = "shift_mirror" if (fixed and bats == "R") else "shift_canonical"
    p_shift = grids[shift_key][rows, cols].mean()
    return float(p_shift - p_std)


def per_batter_table(df: pd.DataFrame, grids: dict, min_per_arm: int) -> pd.DataFrame:
    recs = []
    for bid, sub in df.groupby("batter_id"):
        n_std = int((sub["is_shift"] == 0).sum())
        n_shf = int((sub["is_shift"] == 1).sum())
        if n_std < min_per_arm or n_shf < min_per_arm:
            continue
        r_lift, r_se = realized_lift(sub)
        if np.isnan(r_lift) or r_se == 0 or np.isnan(r_se):
            continue
        bats = sub["bats"].iloc[0] or "?"
        recs.append({
            "batter_id": str(bid),
            "bats": bats,
            "n_std": n_std,
            "n_shift": n_shf,
            "realized_lift": r_lift,
            "realized_se": r_se,
            "pred_lift_fixed": predicted_lift(sub, grids, bats, fixed=True),
            "pred_lift_naive": predicted_lift(sub, grids, bats, fixed=False),
            "pred_lift_optimized": predicted_lift_optimized(sub, grids),
        })
    return pd.DataFrame(recs)


# ── Cross-batter agreement ────────────────────────────────────────────────────

def _wls_slope(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> tuple[float, float]:
    W = w / w.sum()
    xm = np.sum(W * x)
    ym = np.sum(W * y)
    sxx = np.sum(W * (x - xm) ** 2)
    if sxx <= 0:
        return float("nan"), float("nan")
    slope = np.sum(W * (x - xm) * (y - ym)) / sxx
    intercept = ym - slope * xm
    return float(slope), float(intercept)


def agreement(tbl: pd.DataFrame, pred_col: str, bootstrap: int, rng) -> dict:
    x = tbl[pred_col].to_numpy(float)
    y = tbl["realized_lift"].to_numpy(float)
    w = 1.0 / (tbl["realized_se"].to_numpy(float) ** 2)  # inverse-variance
    slope, intercept = _wls_slope(x, y, w)
    # Pearson (weighted) & Spearman (rank) & sign agreement
    W = w / w.sum()
    xm, ym = np.sum(W * x), np.sum(W * y)
    cov = np.sum(W * (x - xm) * (y - ym))
    pear = cov / (np.sqrt(np.sum(W * (x - xm) ** 2) * np.sum(W * (y - ym) ** 2)) + 1e-12)
    sp = pd.Series(x).corr(pd.Series(y), method="spearman")
    sign_agree = float(np.mean(np.sign(x) == np.sign(y)))
    # bootstrap slope over batters
    slopes = np.empty(bootstrap)
    n = len(tbl)
    for b in range(bootstrap):
        idx = rng.integers(0, n, n)
        slopes[b] = _wls_slope(x[idx], y[idx], w[idx])[0]
    lo, hi = np.nanpercentile(slopes, [2.5, 97.5])
    return {
        "n_batters": int(n),
        "slope": slope, "slope_ci95": [float(lo), float(hi)],
        "intercept": intercept,
        "pearson_w": float(pear), "spearman": float(sp),
        "sign_agreement": sign_agree,
        "mean_realized_lift": float(np.average(y, weights=w)),
        "mean_pred_lift": float(np.average(x, weights=w)),
    }


def _verdict(fixed: dict, optimized: dict, opt_by_hand: dict) -> dict:
    """Judged on the engine's PER-BATTER OPTIMIZED recommendation (the actual
    curation), vs the handedness-fixed static template. Pre-registered bar:
    slope∈[0.7,1.3], CI>0, pearson>0. Also reports whether optimization improves
    the correlation with realized lift over the template."""
    def clean_pass(a):
        return (0.7 <= a["slope"] <= 1.3) and a["slope_ci95"][0] > 0 and a["pearson_w"] > 0

    L, R = opt_by_hand.get("L"), opt_by_hand.get("R")
    both_hands_pos = bool(L and R and L["pearson_w"] > 0 and R["pearson_w"] > 0)
    opt_pass = clean_pass(optimized)
    opt_positive = optimized["pearson_w"] > 0 and optimized["slope_ci95"][0] > 0
    improves = optimized["pearson_w"] > fixed["pearson_w"]

    compare = (
        f"Curation vs template: pooled pearson {fixed['pearson_w']:+.2f} (fixed template) → "
        f"{optimized['pearson_w']:+.2f} (per-batter optimized)"
        + (f"; per-hand optimized L {L['pearson_w']:+.2f} / R {R['pearson_w']:+.2f}." if both_hands_pos
           else ".")
    )
    if opt_pass:
        label = ("PASS (per-batter optimized) — the engine's curated shift benefit tracks realized lift "
                 f"(slope {optimized['slope']:+.2f}∈[0.7,1.3], CI>0, pearson {optimized['pearson_w']:+.2f}). " + compare)
    elif opt_positive:
        label = (
            f"PARTIAL PASS (per-batter optimized) — curated predictions POSITIVELY track realized lift "
            f"(pearson {optimized['pearson_w']:+.2f}, spearman {optimized['spearman']:+.2f}, slope "
            f"{optimized['slope']:+.2f} CI [{optimized['slope_ci95'][0]:+.2f},{optimized['slope_ci95'][1]:+.2f}]). "
            + compare + (" Per-batter optimization IMPROVES the correlation with realized lift over the static "
                         "template." if improves else " Optimization does not improve over the template here.")
        )
    else:
        label = "NOT VALIDATED — per-batter optimized predictions do not positively track realized lift. " + compare
    return {
        "label": label,
        "optimized_pass": bool(opt_pass),
        "optimized_positive": bool(opt_positive),
        "improves_over_template": bool(improves),
        "both_hands_positive": both_hands_pos,
    }


# ── Reporting ─────────────────────────────────────────────────────────────────

def print_report(res: dict) -> None:
    print("\n" + "=" * 82)
    print("P1 · PART 1 — engine predicted infield-shift lift vs REALIZED lift (per batter)")
    print("=" * 82)
    print(f"Ground balls 2016–2022, Standard vs Infield shift.  Qualifying batters: {res['n_batters_total']}")
    print(f"  by hand: {res['by_hand_counts']}\n")
    for name, key in [("naive template (pre-fix)", "naive"),
                      ("fixed template (handedness-aware)", "fixed"),
                      ("PER-BATTER OPTIMIZED (curation)", "optimized")]:
        a = res[key]
        print(f"[{name}]  n={a['n_batters']}")
        print(f"    slope {a['slope']:+.3f}  95% CI [{a['slope_ci95'][0]:+.3f}, {a['slope_ci95'][1]:+.3f}]"
              f"   pearson_w {a['pearson_w']:+.3f}  spearman {a['spearman']:+.3f}  sign-agree {a['sign_agreement']:.2f}")
        print(f"    mean realized lift {a['mean_realized_lift']:+.4f}  mean predicted lift {a['mean_pred_lift']:+.4f}")
    print("\n  Per-hand PER-BATTER-OPTIMIZED agreement (predicted vs realized):")
    for hand, a in res["optimized_by_hand"].items():
        print(f"    bats={hand}: n={a['n_batters']:>4}  slope {a['slope']:+.3f}  pearson {a['pearson_w']:+.3f}  "
              f"sign-agree {a['sign_agreement']:.2f}  mean_realized {a['mean_realized_lift']:+.4f}  mean_pred {a['mean_pred_lift']:+.4f}")
    print("\nVERDICT: " + res["verdict"]["label"])
    print("=" * 82 + "\n")


def save_scatter(tbl: pd.DataFrame, path: str) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        logger.warning("matplotlib unavailable: %s", exc)
        return
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2), sharex=False, sharey=True)
    colors = {"L": "#2a7f62", "R": "#b5651d", "S": "#3a6ea5", "?": "gray"}
    for ax, col, title in [(axes[0], "pred_lift_fixed", "fixed template (handedness-aware)"),
                           (axes[1], "pred_lift_optimized", "per-batter optimized (curation)")]:
        for bats, g in tbl.groupby("bats"):
            ax.scatter(g[col], g["realized_lift"], s=8, alpha=0.5,
                       color=colors.get(bats, "gray"), label=f"bats={bats}")
        lim = [min(tbl[col].min(), tbl["realized_lift"].min()) - 0.01,
               max(tbl[col].max(), tbl["realized_lift"].max()) + 0.01]
        ax.plot(lim, lim, "--", color="gray")
        ax.axhline(0, color="k", lw=0.5); ax.axvline(0, color="k", lw=0.5)
        ax.set_xlabel(f"predicted shift lift ({title})")
        ax.set_title(title)
    axes[0].set_ylabel("realized shift lift (out-rate)")
    axes[0].legend(fontsize=8)
    fig.suptitle("P1 Part 1 — predicted vs realized infield-shift lift, per batter")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    logger.info("Scatter → %s", path)


async def main(min_per_arm, bootstrap, out_json, out_plot) -> None:
    rng = np.random.default_rng(42)
    df = await load_ground_balls()
    logger.info("Loaded %d ground balls (2016–2022, Standard/Infield shift)", len(df))
    grids = build_calibrated_grids(df[df["is_shift"] == 0])
    logger.info("Ground calibrator check iso(0,.5,1) = %s", np.round(grids["_iso_slope_check"], 3))

    tbl = per_batter_table(df, grids, min_per_arm)
    if tbl.empty:
        logger.warning("No qualifying batters at min_per_arm=%d. Exiting.", min_per_arm)
        return
    logger.info("Qualifying batters: %d", len(tbl))

    res = {
        "n_batters_total": int(len(tbl)),
        "by_hand_counts": tbl["bats"].value_counts().to_dict(),
        "min_per_arm": min_per_arm,
        "naive": agreement(tbl, "pred_lift_naive", bootstrap, rng),
        "fixed": agreement(tbl, "pred_lift_fixed", bootstrap, rng),
        "optimized": agreement(tbl, "pred_lift_optimized", bootstrap, rng),
        "optimized_by_hand": {
            hand: agreement(g, "pred_lift_optimized", bootstrap, rng)
            for hand, g in tbl.groupby("bats") if len(g) >= 10
        },
    }
    res["verdict"] = _verdict(res["fixed"], res["optimized"], res["optimized_by_hand"])
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
        save_scatter(tbl, out_plot)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-per-arm", type=int, default=40, help="Min ground balls per {Standard, Infield shift} per batter")
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--out-json", type=str, default="/tmp/p1_part1.json")
    parser.add_argument("--out-plot", type=str, default="/tmp/p1_part1_scatter.png")
    args = parser.parse_args()
    asyncio.run(main(args.min_per_arm, args.bootstrap, args.out_json, args.out_plot))
