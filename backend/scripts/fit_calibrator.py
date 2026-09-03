"""
Fit and persist the production out-probability calibrator (per-trajectory
isotonic, coverage → P(out)).

The recalibration experiment (documentation/EXPERIMENTS.md, 2026-09-02, PASS)
validated the method out-of-fold but deliberately discarded the fitted maps.
This script creates the shipping artifact:

  1. RELIABILITY GATE (pre-registered kill criterion, ROADMAP P0): re-run the
     LOSO out-of-fold calibration on fit-time data and require pooled
     reliability slope ∈ [0.9, 1.1]. If the gate fails, NO artifact is written
     — return to the recalibration experiment instead of shipping.
  2. Fit final per-trajectory isotonic maps on ALL standard-alignment balls.
  3. Persist a versioned JSON artifact (thresholds + fit metadata + gate
     results) into app/services/alignment/artifacts/, loaded at serve time by
     services/alignment/calibration.py.

Usage:
    cd backend
    python -m scripts.fit_calibrator                       # all seasons, v1
    python -m scripts.fit_calibrator --report-json documentation-artifact-path
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import date

import numpy as np

from app.services.alignment.calibration import ARTIFACT_DIR, OutCalibrator
from scripts.eval_out_model import all_metrics, calibration, engine_p_out, load_balls
from scripts.eval_recalibrated import apply_calibrators, fit_calibrators

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("fit_calibrator")

SLOPE_BOUNDS = (0.9, 1.1)  # pre-registered reliability gate (ROADMAP P0 kill criterion)


def oof_gate(df) -> dict:
    """LOSO out-of-fold reliability check on fit-time data (mirrors the
    validated experiment: fit isotonic per trajectory on train seasons, predict
    the held-out season, pool)."""
    seasons = sorted(int(s) for s in df["season"].unique())
    p_oof = np.empty(len(df))
    for s in seasons:
        test_mask = (df["season"] == s).to_numpy()
        cals = fit_calibrators("isotonic", df[~test_mask])
        p_oof[test_mask] = apply_calibrators(cals, df[test_mask])
    y = df["y"].to_numpy()
    cal = calibration(y, p_oof)
    ok = SLOPE_BOUNDS[0] <= cal["slope"] <= SLOPE_BOUNDS[1]
    return {
        "seasons": seasons,
        "slope": cal["slope"],
        "intercept": cal["intercept"],
        "metrics": all_metrics(y, p_oof),
        "slope_bounds": list(SLOPE_BOUNDS),
        "pass": bool(ok),
    }


def extract_thresholds(fitted) -> dict:
    """Pull sklearn isotonic thresholds so serving needs only np.interp."""
    kind, m = fitted
    assert kind == "isotonic"
    return {
        "x": [float(v) for v in m.X_thresholds_],
        "y": [float(v) for v in m.y_thresholds_],
    }


async def main(seasons, version, out_path, report_json) -> None:
    df = await load_balls(seasons, alignment_mode="standard")
    if df.empty:
        raise SystemExit("No standard-alignment balls — backfill alignment first.")
    df["p_raw"] = engine_p_out(df)
    logger.info("Loaded %d standard-alignment balls, seasons %s",
                len(df), sorted(df["season"].unique()))

    gate = oof_gate(df)
    logger.info("OOF reliability gate: slope=%.3f (bounds %s) → %s",
                gate["slope"], gate["slope_bounds"], "PASS" if gate["pass"] else "FAIL")
    if not gate["pass"]:
        raise SystemExit(
            f"RELIABILITY GATE FAILED: OOF slope {gate['slope']:.3f} outside "
            f"{SLOPE_BOUNDS} — artifact NOT written. Return to the recalibration "
            "experiment (documentation/EXPERIMENTS.md) before shipping."
        )

    # Final maps: fit on ALL data (the OOF gate above is the honesty check;
    # the shipped map should use every ball).
    final = fit_calibrators("isotonic", df)
    artifact = {
        "artifact": "out_calibrator",
        "version": version,
        "method": "isotonic_per_trajectory",
        "fit_date": date.today().isoformat(),
        "data": {
            "population": "standard-alignment in-play batted balls, HR excluded",
            "seasons": gate["seasons"],
            "n": int(len(df)),
            "out_rate": float(df["y"].mean()),
        },
        "oof_gate": gate,
        "calibrators": {name: extract_thresholds(final[name]) for name in ("ground", "air")},
    }

    ARTIFACT_DIR.mkdir(exist_ok=True)
    path = out_path or (ARTIFACT_DIR / f"out_calibrator_{version}.json")
    with open(path, "w") as f:
        json.dump(artifact, f)
    logger.info("Artifact → %s", path)

    # Round-trip sanity: load through the serving code path and spot-check that
    # np.interp reproduces sklearn's predictions on the fit data.
    cal = OutCalibrator.load(path)
    from scripts.eval_recalibrated import _air_mask
    air = _air_mask(df["ball_trajectory"])
    for name, mask in (("ground", ~air), ("air", air)):
        p_raw = df.loc[mask, "p_raw"].to_numpy()[:5000]
        skl = np.clip(final[name][1].predict(p_raw), 0.0, 1.0)
        served = cal.apply(p_raw, name)
        max_dev = float(np.max(np.abs(skl - served)))
        logger.info("Round-trip %s: max |sklearn − np.interp| = %.2e", name, max_dev)
        assert max_dev < 1e-9, f"serving path diverges from sklearn ({name})"

    if report_json:
        report = {k: v for k, v in artifact.items() if k != "calibrators"}
        report["artifact_path"] = str(path)
        with open(report_json, "w") as f:
            json.dump(report, f, indent=2)
        logger.info("Fit report → %s", report_json)

    print(f"\nCalibrator {version} written: {path}")
    print(f"  n={len(df):,}  seasons={gate['seasons']}")
    print(f"  OOF gate: slope={gate['slope']:.3f}  log_loss={gate['metrics']['log_loss']:.5f}  → PASS")
    for name in ("ground", "air"):
        t = artifact["calibrators"][name]
        print(f"  {name}: {len(t['x'])} thresholds, g(0)={t['y'][0]:.4f}, g(max)={t['y'][-1]:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=int, nargs="+", help="default: all backfilled")
    parser.add_argument("--version", type=str, default="v1")
    parser.add_argument("--out", type=str, default=None, help="artifact path override")
    parser.add_argument("--report-json", type=str,
                        default="../documentation/artifacts/calibrator_fit_report.json")
    args = parser.parse_args()
    asyncio.run(main(args.seasons, args.version, args.out, args.report_json))
