"""
Build the league-average landing-density artifact (shrinkage prior + no-data
fallback for the empirical landing path — see services/alignment/landing.py).

Population matches the calibrator fit estimand: in-play hit/out batted balls,
HR excluded, hc and trajectory present (all alignments — a batter's landing
distribution is used regardless of how the defense stood).

Usage:
    cd backend && python -m scripts.build_league_landing
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import date

import numpy as np
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.pitch_appearance import PitchAppearance
from app.services.alignment.landing import (
    AIR_TRAJECTORIES,
    GRID,
    LEAGUE_ARTIFACT,
    _gaussian_blur,
    hc_to_cell,
)
import app.models  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("build_league_landing")


async def main(seasons, out_path) -> None:
    stmt = select(
        PitchAppearance.hc_x, PitchAppearance.hc_y, PitchAppearance.ball_trajectory,
        PitchAppearance.season,
    ).where(
        PitchAppearance.general_result.in_(("hit", "out")),
        PitchAppearance.specific_result != "hr",
        PitchAppearance.hc_x.is_not(None),
        PitchAppearance.hc_y.is_not(None),
        PitchAppearance.ball_trajectory.is_not(None),
    )
    if seasons:
        stmt = stmt.where(PitchAppearance.season.in_(seasons))
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(stmt)).all()
    logger.info("Loaded %d batted balls", len(rows))

    hc_x = np.array([r[0] for r in rows], dtype=float)
    hc_y = np.array([r[1] for r in rows], dtype=float)
    is_air = np.array([r[2] in AIR_TRAJECTORIES for r in rows])
    season = np.array([r[3] for r in rows], dtype=float)
    row_i, col_i = hc_to_cell(hc_x, hc_y, season)

    artifact = {"artifact": "league_landing", "version": "v2",
                "fit_date": date.today().isoformat(), "n": int(len(rows)),
                "ground_share": float((~is_air).mean())}
    for name, mask in (("ground", ~is_air), ("air", is_air)):
        h = np.zeros((GRID, GRID), dtype=np.float64)
        np.add.at(h, (row_i[mask], col_i[mask]), 1.0)
        h = _gaussian_blur(h, 1.0)  # light smoothing only — 1.5M balls is dense
        h /= h.sum()
        artifact[name] = np.round(h, 8).tolist()
        artifact[f"n_{name}"] = int(mask.sum())

    path = out_path or LEAGUE_ARTIFACT
    with open(path, "w") as f:
        json.dump(artifact, f)
    logger.info("League landing artifact → %s (ground n=%d, air n=%d, ground_share=%.4f)",
                path, artifact["n_ground"], artifact["n_air"], artifact["ground_share"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=int, nargs="+")
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()
    asyncio.run(main(args.seasons, args.out))
