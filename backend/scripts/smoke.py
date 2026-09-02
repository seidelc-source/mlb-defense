"""
End-to-end smoke test against a running backend + populated database.

Checks: health → player search → spray chart → alignment recommend →
custom score → alignment history. Exits non-zero on first failure.

Usage:
    cd backend
    python -m scripts.smoke [--base http://localhost:8000]
"""
import argparse
import sys

import httpx


def fail(msg: str) -> None:
    print(f"  FAIL: {msg}")
    sys.exit(1)


def main(base: str) -> None:
    client = httpx.Client(base_url=base, timeout=30)

    print("1. Health check")
    r = client.get("/health")
    if r.status_code != 200 or r.json().get("status") != "ok":
        fail(f"health returned {r.status_code}")
    print("  ok")

    print("2. Player search")
    r = client.get("/api/v1/players", params={"limit": 200})
    if r.status_code != 200:
        fail(f"players returned {r.status_code}")
    players = r.json()["players"]
    if not players:
        fail("no players — run scripts.ingest_all first")
    print(f"  ok ({r.json()['total']} players)")

    print("3. Find a batter with spray data")
    batter = None
    for p in players:
        r = client.get(f"/api/v1/spray/{p['id']}", params={"season": 2024})
        if r.status_code == 200:
            batter = p
            spray = r.json()
            break
    if batter is None:
        fail("no batter with sufficient spray data found")
    print(f"  ok ({batter['full_name']}, n={spray['sample_n']})")

    print("4. Alignment recommendation")
    pitcher = next((p for p in players if p["position"] == "P"), players[0])
    r = client.get("/api/v1/stadiums")
    stadiums = r.json()
    if not stadiums:
        fail("no stadiums — run scripts.seed first")
    team_id = batter.get("team_id") or players[0].get("team_id")
    r = client.post(
        "/api/v1/alignments/recommend",
        json={
            "team_id": str(team_id),
            "batter_id": batter["id"],
            "pitcher_id": pitcher["id"],
            "stadium_id": stadiums[0]["id"],
        },
    )
    if r.status_code != 200:
        fail(f"recommend returned {r.status_code}: {r.text[:200]}")
    rec = r.json()
    if "fielder_positions" not in rec or len(rec["fielder_positions"]) < 7:
        fail("recommendation missing fielder positions")
    print(f"  ok (shift={rec['shift_type']}, delta={rec['predicted_oaa_delta']})")

    print("5. Custom alignment scoring")
    positions = {
        pos: {"x": fp["x"], "y": fp["y"]}
        for pos, fp in rec["fielder_positions"].items()
    }
    r = client.post(
        "/api/v1/alignments/score",
        json={"batter_id": batter["id"], "positions": positions},
    )
    if r.status_code != 200:
        fail(f"score returned {r.status_code}: {r.text[:200]}")
    score = r.json()
    if not score["legal"]:
        fail(f"recommended alignment scored as illegal: {score['illegal_positions']}")
    print(f"  ok (delta={score['predicted_oaa_delta']}, legal={score['legal']})")

    print("6. Alignment history")
    r = client.get("/api/v1/alignments", params={"batter_id": batter["id"], "limit": 5})
    if r.status_code != 200:
        fail(f"history returned {r.status_code}")
    print(f"  ok ({len(r.json())} records)")

    print("\nSmoke test passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    args = parser.parse_args()
    main(args.base)
