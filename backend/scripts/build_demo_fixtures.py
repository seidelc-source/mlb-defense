"""Generate static demo fixtures for the GitHub Pages build.

Hits a RUNNING local backend (uvicorn + seeded DB) and writes prebaked JSON
responses under frontend/public/demo-data/, matching the fixture layout that
frontend/src/demo/adapter.ts resolves at runtime.

Usage:
    cd backend && python -m scripts.build_demo_fixtures [--api http://localhost:8000/api/v1]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

OUT_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "demo-data"
FIELD_POSITIONS = ["1B", "2B", "SS", "3B", "LF", "CF", "RF"]
OPTIMIZE_FOR = ["balanced", "prevent_hit", "prevent_extra_base"]
# Must mirror what the UI sends (FieldView.handleRequestAlignment)
INCLUDE_FACTORS = ["pitcher_type", "batter_spray", "weather", "injury", "stadium"]
SPRAY_HANDS = ["all", "R", "L"]

# (batter name, pitcher name, fielding team abbreviation) — pitcher's team
# fields the defense in its home park. Missing players are skipped with a
# warning so the script survives roster churn.
MATCHUPS = [
    ("Aaron Judge", "Tarik Skubal", "DET"),
    ("Shohei Ohtani", "Paul Skenes", "PIT"),
    ("Kyle Schwarber", "Framber Valdez", "HOU"),
    ("Juan Soto", "Logan Webb", "SF"),
    ("Freddie Freeman", "Kyle Freeland", "COL"),
    ("Vladimir Guerrero Jr.", "Garrett Crochet", "BOS"),
    ("Luis Arraez", "Zack Wheeler", "PHI"),
]

WEATHER_PRESETS: list[dict[str, Any]] = [
    {"id": "off", "label": "Clear"},
    {
        "id": "hot",
        "label": "Hot day 95°F",
        "input": {"temperature_f": 95, "humidity_pct": 60, "wind_speed_mph": 3, "wind_direction_deg": 180},
    },
    {
        "id": "wind_out",
        "label": "Wind out 18mph",
        "input": {"temperature_f": 78, "humidity_pct": 45, "wind_speed_mph": 18, "wind_direction_deg": 180},
    },
    {
        "id": "wind_in",
        "label": "Wind in 15mph",
        "input": {"temperature_f": 62, "humidity_pct": 55, "wind_speed_mph": 15, "wind_direction_deg": 0},
    },
    {
        "id": "cross",
        "label": "Cross L→R 14mph",
        "input": {"temperature_f": 72, "humidity_pct": 50, "wind_speed_mph": 14, "wind_direction_deg": 270},
    },
]


def write(rel: str, data: Any) -> None:
    path = OUT_DIR / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":")))


def slugify(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-").split("-")[-1]


class Api:
    def __init__(self, base: str):
        self.client = httpx.Client(base_url=base, timeout=60)

    def get(self, path: str, **params: Any) -> Any:
        r = self.client.get(path, params={k: v for k, v in params.items() if v is not None})
        r.raise_for_status()
        return r.json()

    def get_or_none(self, path: str, **params: Any) -> Any:
        r = self.client.get(path, params={k: v for k, v in params.items() if v is not None})
        return r.json() if r.status_code == 200 else None

    def post(self, path: str, body: Any, **params: Any) -> Any:
        r = self.client.post(path, json=body, params=params or None)
        r.raise_for_status()
        return r.json()


def resolve_player(api: Api, name: str, role: str) -> dict | None:
    res = api.get("/players", name=name, role=role, active=True, limit=10)
    players = res["players"]
    exact = [p for p in players if p["full_name"].lower() == name.lower()]
    pick = exact[0] if exact else (players[0] if players else None)
    if pick and not exact:
        print(f"  ! no exact match for {name!r}; using {pick['full_name']!r}")
    return pick


def dump_player(api: Api, player: dict, spray: bool) -> None:
    pid = player["id"]
    base = f"players/{pid}"
    write(f"{base}/detail.json", api.get(f"/players/{pid}"))

    fseasons = api.get(f"/players/{pid}/fielding/seasons")
    write(f"{base}/fielding_seasons.json", fseasons)
    # Cover the UI's hardcoded default season even when the player has no data
    for season in sorted(set(fseasons) | {2024, 2025}):
        data = api.get_or_none(f"/players/{pid}/fielding", season=season) or []
        write(f"{base}/fielding_s{season}.json", data)

    pseasons = api.get(f"/players/{pid}/pitching/seasons")
    write(f"{base}/pitching_seasons.json", pseasons)
    for season in pseasons:
        data = api.get_or_none(f"/players/{pid}/pitching", season=season)
        if data:
            write(f"{base}/pitching_s{season}.json", data)

    rng = api.get_or_none(f"/range/{pid}", position=player["position"], season=2024)
    if rng:
        write(f"{base}/range.json", rng)

    if spray:
        seasons = api.get_or_none(f"/spray/{pid}/seasons") or []
        write(f"spray/{pid}/seasons.json", seasons)
        for season in [*seasons, 0]:
            for hand in SPRAY_HANDS:
                data = api.get_or_none(
                    f"/spray/{pid}",
                    season=season,
                    pitcher_hand=None if hand == "all" else hand,
                )
                if data:
                    write(f"spray/{pid}/s{season}_h{hand}.json", data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000/api/v1")
    args = parser.parse_args()
    api = Api(args.api)

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    teams = api.get("/teams")
    write("teams.json", teams)
    stadiums = api.get("/stadiums")
    write("stadiums.json", stadiums)
    team_by_abbrev = {t["abbreviation"]: t for t in teams}

    matchups: list[dict] = []
    featured_players: dict[str, dict] = {}
    rosters: dict[str, list] = {}

    for batter_name, pitcher_name, abbrev in MATCHUPS:
        team = team_by_abbrev.get(abbrev)
        batter = resolve_player(api, batter_name, "batter")
        pitcher = resolve_player(api, pitcher_name, "pitcher")
        if not (team and batter and pitcher and team.get("home_stadium_id")):
            print(f"  ! skipping matchup {batter_name} vs {pitcher_name} @ {abbrev} (unresolved)")
            continue
        stadium = next((s for s in stadiums if s["id"] == team["home_stadium_id"]), None)
        if not stadium:
            print(f"  ! skipping {abbrev}: home stadium not found")
            continue
        matchups.append(
            {
                "id": f"{slugify(batter['full_name'])}-{slugify(pitcher['full_name'])}",
                "label": f"{batter['full_name']} vs {pitcher['full_name']} @ {stadium['name']}",
                "batter_id": batter["id"],
                "pitcher_id": pitcher["id"],
                "team_id": team["id"],
                "batting_team_id": batter["team_id"] or "",
                "stadium_id": stadium["id"],
            }
        )
        featured_players[batter["id"]] = batter
        featured_players[pitcher["id"]] = pitcher
        if team["id"] not in rosters:
            rosters[team["id"]] = api.get(f"/teams/{team['id']}/roster")
            write(f"rosters/{team['id']}.json", rosters[team["id"]])
        write(f"layouts/{stadium['id']}.json", api.get(f"/stadiums/{stadium['id']}/layout"))

    print(f"{len(matchups)} matchups resolved")

    print("Dumping player fixtures…")
    for p in featured_players.values():
        print(f"  {p['full_name']}")
        dump_player(api, p, spray=p["position"] != "P")

    print("Weather previews…")
    for m in matchups:
        for preset in WEATHER_PRESETS:
            if "input" not in preset:
                continue
            data = api.post("/weather/preview", preset["input"], stadium_id=m["stadium_id"])
            write(f"weather/{m['stadium_id']}__{preset['id']}.json", data)

    print("Alignments…")
    model_version = calibrator_version = None
    for m in matchups:
        roster = rosters[m["team_id"]]
        active_roster = [
            {"player_id": p["id"], "position": pos}
            for pos in FIELD_POSITIONS
            if (p := next((r for r in roster if r["position"] == pos), None))
        ]
        for preset in WEATHER_PRESETS:
            for opt in OPTIMIZE_FOR:
                body = {
                    "team_id": m["team_id"],
                    "batter_id": m["batter_id"],
                    "pitcher_id": m["pitcher_id"],
                    "stadium_id": m["stadium_id"],
                    "inning": 1,
                    "outs": 0,
                    "runners": {"on_1b": False, "on_2b": False, "on_3b": False},
                    "score_diff": 0,
                    "active_roster": active_roster,
                    "optimize_for": opt,
                    "include_factors": INCLUDE_FACTORS,
                }
                if "input" in preset:
                    body["weather"] = preset["input"]
                res = api.post("/alignments/recommend", body)
                model_version = res.get("model_version", model_version)
                calibrator_version = res.get("calibrator_version", calibrator_version)
                write(f"alignments/{m['id']}__{preset['id']}__{opt}.json", res)
        print(f"  {m['label']}")

    write(
        "manifest.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model_version": model_version,
            "calibrator_version": calibrator_version,
            "matchups": matchups,
            "weather_presets": WEATHER_PRESETS,
            "players": sorted(featured_players.values(), key=lambda p: p["full_name"]),
        },
    )

    n_files = sum(1 for _ in OUT_DIR.rglob("*.json"))
    size_mb = sum(f.stat().st_size for f in OUT_DIR.rglob("*.json")) / 1e6
    print(f"Done: {n_files} fixtures, {size_mb:.1f} MB → {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
