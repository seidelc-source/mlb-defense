"""Fit and persist the angular-corridor ground-out artifact (ang-v1).

Gate G1 of the shipping experiment (documentation/EXPERIMENTS.md 2026-09-10):
LOSO out-of-fold reliability slope must be in [0.9, 1.1] on standard-alignment
grounders or NO artifact is written. Fit population: all seasons, corrected
frame, Standard alignment, hit/out grounders, ny >= MIN_NY.

Usage:
    cd backend && python -m scripts.fit_angular_ground \
        --report-json ../documentation/artifacts/angular_ground_fit_report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import date

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.pitch_appearance import PitchAppearance
from app.services.alignment.angular import ARTIFACT_DIR, AngularGroundModel, station_angles
from app.services.alignment.engine import STANDARD_POSITIONS
from app.services.alignment.landing import hc_to_norm
from scripts.eval_out_model import calibration
import app.models  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("fit_angular_ground")

MIN_NY = 0.05
SLOPE_BOUNDS = (0.9, 1.1)
VERSION = "ang-v1"


async def load_standard_grounders() -> pd.DataFrame:
    stmt = select(
        PitchAppearance.hc_x,
        PitchAppearance.hc_y,
        PitchAppearance.season,
        PitchAppearance.general_result,
    ).where(
        PitchAppearance.ball_trajectory == "groundball",
        PitchAppearance.if_fielding_alignment == "Standard",
        PitchAppearance.general_result.in_(("hit", "out")),
        PitchAppearance.hc_x.is_not(None),
        PitchAppearance.hc_y.is_not(None),
    )
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(stmt)).mappings().all()
    df = pd.DataFrame(rows)
    df["y"] = (df["general_result"] == "out").astype(int)
    nx, ny = hc_to_norm(
        df["hc_x"].to_numpy(float), df["hc_y"].to_numpy(float), df["season"].to_numpy(float)
    )
    df["theta"] = np.arctan2(nx - 0.5, ny)
    df = df[ny >= MIN_NY].reset_index(drop=True)
    stations = station_angles(STANDARD_POSITIONS)
    df["feature"] = np.min(
        np.abs(df["theta"].to_numpy()[:, None] - stations[None, :]), axis=1
    )
    return df


def fit(feature: np.ndarray, y: np.ndarray) -> IsotonicRegression:
    iso = IsotonicRegression(increasing=False, out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(feature, y)
    return iso


async def main(report_json: str | None) -> None:
    df = await load_standard_grounders()
    logger.info("standard grounders (ny >= %.2f): %d, seasons %s",
                MIN_NY, len(df), sorted(df["season"].unique()))

    # G1: LOSO out-of-fold reliability gate
    p_oof = np.empty(len(df))
    for s in sorted(df["season"].unique()):
        te = (df["season"] == s).to_numpy()
        iso = fit(df.loc[~te, "feature"].to_numpy(), df.loc[~te, "y"].to_numpy())
        p_oof[te] = iso.predict(df.loc[te, "feature"].to_numpy())
    gate = calibration(df["y"].to_numpy(), p_oof)
    ok = SLOPE_BOUNDS[0] <= gate["slope"] <= SLOPE_BOUNDS[1]
    logger.info("G1 LOSO reliability: slope=%.3f (bounds %s) → %s",
                gate["slope"], SLOPE_BOUNDS, "PASS" if ok else "FAIL")
    if not ok:
        raise SystemExit("G1 FAILED — artifact NOT written; return to the shipping experiment.")

    final = fit(df["feature"].to_numpy(), df["y"].to_numpy())
    artifact = {
        "artifact": "angular_ground",
        "version": VERSION,
        "fit_date": date.today().isoformat(),
        "data": {
            "population": "standard-alignment hit/out grounders, corrected frame, ny>=%.2f" % MIN_NY,
            "seasons": sorted(int(s) for s in df["season"].unique()),
            "n": int(len(df)),
            "out_rate": float(df["y"].mean()),
        },
        "loso_gate": {"slope": gate["slope"], "intercept": gate["intercept"],
                      "bounds": list(SLOPE_BOUNDS), "pass": True},
        "stations": {p: list(STANDARD_POSITIONS[p]) for p in ("1B", "2B", "SS", "3B")},
        "x": [float(v) for v in final.X_thresholds_],
        "y": [float(v) for v in final.y_thresholds_],
    }
    path = ARTIFACT_DIR / "angular_ground_v1.json"
    with open(path, "w") as f:
        json.dump(artifact, f)
    logger.info("Artifact → %s (%d thresholds, g(0)=%.3f, g(max)=%.3f)",
                path, len(artifact["x"]), artifact["y"][0], artifact["y"][-1])

    # Round-trip: serving np.interp must reproduce sklearn on the fit data
    model = AngularGroundModel.load(path)
    sample = df["feature"].to_numpy()[:5000]
    dev = float(np.max(np.abs(final.predict(sample) - model.p_out(sample))))
    assert dev < 1e-9, f"serving path diverges from sklearn ({dev})"
    logger.info("Round-trip max |sklearn − np.interp| = %.2e", dev)

    if report_json:
        rep = {k: v for k, v in artifact.items() if k not in ("x", "y")}
        rep["artifact_path"] = str(path)
        with open(report_json, "w") as f:
            json.dump(rep, f, indent=2)
        logger.info("Fit report → %s", report_json)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-json", default=None)
    args = parser.parse_args()
    asyncio.run(main(args.report_json))
