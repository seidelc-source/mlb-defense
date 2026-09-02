"""
Seed script — populates teams and stadiums with real MLB data.

Usage:
    cd backend
    python -m scripts.seed
"""
import asyncio
import uuid

from app.core.database import AsyncSessionLocal, engine
from app.models.base import Base
from app.models.stadium import Stadium
from app.models.team import Team

STADIUMS = [
    {"mlb_venue_id": "15", "name": "Chase Field", "city": "Phoenix", "state": "AZ", "lat": 33.4455, "lon": -112.0667, "alt": 1082, "roof": "retractable", "surface": "grass", "lf": 330, "cf": 407, "rf": 334},
    {"mlb_venue_id": "4705", "name": "Truist Park", "city": "Atlanta", "state": "GA", "lat": 33.8907, "lon": -84.4677, "alt": 1050, "roof": "open", "surface": "grass", "lf": 335, "cf": 400, "rf": 325},
    {"mlb_venue_id": "2", "name": "Oriole Park at Camden Yards", "city": "Baltimore", "state": "MD", "lat": 39.2838, "lon": -76.6216, "alt": 30, "roof": "open", "surface": "grass", "lf": 333, "cf": 400, "rf": 318},
    {"mlb_venue_id": "3", "name": "Fenway Park", "city": "Boston", "state": "MA", "lat": 42.3467, "lon": -71.0972, "alt": 20, "roof": "open", "surface": "grass", "lf": 310, "cf": 390, "rf": 302},
    {"mlb_venue_id": "17", "name": "Wrigley Field", "city": "Chicago", "state": "IL", "lat": 41.9484, "lon": -87.6553, "alt": 595, "roof": "open", "surface": "grass", "lf": 355, "cf": 400, "rf": 353},
    {"mlb_venue_id": "4", "name": "Guaranteed Rate Field", "city": "Chicago", "state": "IL", "lat": 41.8299, "lon": -87.6338, "alt": 595, "roof": "open", "surface": "grass", "lf": 330, "cf": 400, "rf": 335},
    {"mlb_venue_id": "2602", "name": "Great American Ball Park", "city": "Cincinnati", "state": "OH", "lat": 39.0975, "lon": -84.5069, "alt": 490, "roof": "open", "surface": "grass", "lf": 328, "cf": 404, "rf": 325},
    {"mlb_venue_id": "5", "name": "Progressive Field", "city": "Cleveland", "state": "OH", "lat": 41.4962, "lon": -81.6852, "alt": 660, "roof": "open", "surface": "grass", "lf": 325, "cf": 405, "rf": 325},
    {"mlb_venue_id": "19", "name": "Coors Field", "city": "Denver", "state": "CO", "lat": 39.7561, "lon": -104.9942, "alt": 5200, "roof": "open", "surface": "grass", "lf": 347, "cf": 415, "rf": 350},
    {"mlb_venue_id": "2394", "name": "Comerica Park", "city": "Detroit", "state": "MI", "lat": 42.3390, "lon": -83.0485, "alt": 600, "roof": "open", "surface": "grass", "lf": 345, "cf": 420, "rf": 330},
    {"mlb_venue_id": "2392", "name": "Minute Maid Park", "city": "Houston", "state": "TX", "lat": 29.7573, "lon": -95.3555, "alt": 42, "roof": "retractable", "surface": "grass", "lf": 315, "cf": 409, "rf": 326},
    {"mlb_venue_id": "7", "name": "Kauffman Stadium", "city": "Kansas City", "state": "MO", "lat": 39.0517, "lon": -94.4803, "alt": 750, "roof": "open", "surface": "grass", "lf": 330, "cf": 410, "rf": 330},
    {"mlb_venue_id": "1", "name": "Angel Stadium", "city": "Anaheim", "state": "CA", "lat": 33.8003, "lon": -117.8827, "alt": 160, "roof": "open", "surface": "grass", "lf": 330, "cf": 400, "rf": 330},
    {"mlb_venue_id": "22", "name": "Dodger Stadium", "city": "Los Angeles", "state": "CA", "lat": 34.0739, "lon": -118.2400, "alt": 515, "roof": "open", "surface": "grass", "lf": 330, "cf": 395, "rf": 330},
    {"mlb_venue_id": "4169", "name": "loanDepot park", "city": "Miami", "state": "FL", "lat": 25.7781, "lon": -80.2197, "alt": 7, "roof": "retractable", "surface": "grass", "lf": 344, "cf": 407, "rf": 335},
    {"mlb_venue_id": "32", "name": "American Family Field", "city": "Milwaukee", "state": "WI", "lat": 43.0280, "lon": -87.9712, "alt": 600, "roof": "retractable", "surface": "grass", "lf": 344, "cf": 400, "rf": 345},
    {"mlb_venue_id": "3312", "name": "Target Field", "city": "Minneapolis", "state": "MN", "lat": 44.9817, "lon": -93.2776, "alt": 830, "roof": "open", "surface": "grass", "lf": 339, "cf": 404, "rf": 328},
    {"mlb_venue_id": "3289", "name": "Citi Field", "city": "New York", "state": "NY", "lat": 40.7571, "lon": -73.8458, "alt": 20, "roof": "open", "surface": "grass", "lf": 335, "cf": 408, "rf": 330},
    {"mlb_venue_id": "3313", "name": "Yankee Stadium", "city": "Bronx", "state": "NY", "lat": 40.8296, "lon": -73.9262, "alt": 55, "roof": "open", "surface": "grass", "lf": 318, "cf": 408, "rf": 314},
    {"mlb_venue_id": "2529", "name": "Sutter Health Park", "city": "West Sacramento", "state": "CA", "lat": 38.5803, "lon": -121.5133, "alt": 20, "roof": "open", "surface": "grass", "lf": 330, "cf": 403, "rf": 325},
    {"mlb_venue_id": "2681", "name": "Citizens Bank Park", "city": "Philadelphia", "state": "PA", "lat": 39.9061, "lon": -75.1665, "alt": 20, "roof": "open", "surface": "grass", "lf": 329, "cf": 401, "rf": 330},
    {"mlb_venue_id": "31", "name": "PNC Park", "city": "Pittsburgh", "state": "PA", "lat": 40.4469, "lon": -80.0057, "alt": 730, "roof": "open", "surface": "grass", "lf": 325, "cf": 399, "rf": 320},
    {"mlb_venue_id": "2680", "name": "Petco Park", "city": "San Diego", "state": "CA", "lat": 32.7076, "lon": -117.1570, "alt": 14, "roof": "open", "surface": "grass", "lf": 336, "cf": 396, "rf": 322},
    {"mlb_venue_id": "2395", "name": "Oracle Park", "city": "San Francisco", "state": "CA", "lat": 37.7786, "lon": -122.3893, "alt": 5, "roof": "open", "surface": "grass", "lf": 339, "cf": 399, "rf": 309},
    {"mlb_venue_id": "680", "name": "T-Mobile Park", "city": "Seattle", "state": "WA", "lat": 47.5914, "lon": -122.3325, "alt": 20, "roof": "retractable", "surface": "grass", "lf": 331, "cf": 405, "rf": 326},
    {"mlb_venue_id": "2889", "name": "Busch Stadium", "city": "St. Louis", "state": "MO", "lat": 38.6226, "lon": -90.1928, "alt": 455, "roof": "open", "surface": "grass", "lf": 336, "cf": 400, "rf": 335},
    {"mlb_venue_id": "12", "name": "Tropicana Field", "city": "St. Petersburg", "state": "FL", "lat": 27.7682, "lon": -82.6534, "alt": 44, "roof": "dome", "surface": "turf", "lf": 315, "cf": 404, "rf": 322},
    {"mlb_venue_id": "13", "name": "Globe Life Field", "city": "Arlington", "state": "TX", "lat": 32.7472, "lon": -97.0844, "alt": 550, "roof": "retractable", "surface": "grass", "lf": 329, "cf": 407, "rf": 326},
    {"mlb_venue_id": "14", "name": "Rogers Centre", "city": "Toronto", "state": "ON", "lat": 43.6414, "lon": -79.3894, "alt": 270, "roof": "retractable", "surface": "turf", "lf": 328, "cf": 400, "rf": 328},
    {"mlb_venue_id": "3309", "name": "Nationals Park", "city": "Washington", "state": "DC", "lat": 38.8730, "lon": -77.0074, "alt": 25, "roof": "open", "surface": "grass", "lf": 336, "cf": 402, "rf": 335},
]

TEAMS = [
    {"mlb_id": "109", "name": "Arizona Diamondbacks", "abbr": "ARI", "league": "NL", "div": "West", "venue": "15"},
    {"mlb_id": "144", "name": "Atlanta Braves", "abbr": "ATL", "league": "NL", "div": "East", "venue": "4705"},
    {"mlb_id": "110", "name": "Baltimore Orioles", "abbr": "BAL", "league": "AL", "div": "East", "venue": "2"},
    {"mlb_id": "111", "name": "Boston Red Sox", "abbr": "BOS", "league": "AL", "div": "East", "venue": "3"},
    {"mlb_id": "112", "name": "Chicago Cubs", "abbr": "CHC", "league": "NL", "div": "Central", "venue": "17"},
    {"mlb_id": "145", "name": "Chicago White Sox", "abbr": "CWS", "league": "AL", "div": "Central", "venue": "4"},
    {"mlb_id": "113", "name": "Cincinnati Reds", "abbr": "CIN", "league": "NL", "div": "Central", "venue": "2602"},
    {"mlb_id": "114", "name": "Cleveland Guardians", "abbr": "CLE", "league": "AL", "div": "Central", "venue": "5"},
    {"mlb_id": "115", "name": "Colorado Rockies", "abbr": "COL", "league": "NL", "div": "West", "venue": "19"},
    {"mlb_id": "116", "name": "Detroit Tigers", "abbr": "DET", "league": "AL", "div": "Central", "venue": "2394"},
    {"mlb_id": "117", "name": "Houston Astros", "abbr": "HOU", "league": "AL", "div": "West", "venue": "2392"},
    {"mlb_id": "118", "name": "Kansas City Royals", "abbr": "KC", "league": "AL", "div": "Central", "venue": "7"},
    {"mlb_id": "108", "name": "Los Angeles Angels", "abbr": "LAA", "league": "AL", "div": "West", "venue": "1"},
    {"mlb_id": "119", "name": "Los Angeles Dodgers", "abbr": "LAD", "league": "NL", "div": "West", "venue": "22"},
    {"mlb_id": "146", "name": "Miami Marlins", "abbr": "MIA", "league": "NL", "div": "East", "venue": "4169"},
    {"mlb_id": "158", "name": "Milwaukee Brewers", "abbr": "MIL", "league": "NL", "div": "Central", "venue": "32"},
    {"mlb_id": "142", "name": "Minnesota Twins", "abbr": "MIN", "league": "AL", "div": "Central", "venue": "3312"},
    {"mlb_id": "121", "name": "New York Mets", "abbr": "NYM", "league": "NL", "div": "East", "venue": "3289"},
    {"mlb_id": "147", "name": "New York Yankees", "abbr": "NYY", "league": "AL", "div": "East", "venue": "3313"},
    {"mlb_id": "133", "name": "Athletics", "abbr": "ATH", "league": "AL", "div": "West", "venue": "2529"},
    {"mlb_id": "143", "name": "Philadelphia Phillies", "abbr": "PHI", "league": "NL", "div": "East", "venue": "2681"},
    {"mlb_id": "134", "name": "Pittsburgh Pirates", "abbr": "PIT", "league": "NL", "div": "Central", "venue": "31"},
    {"mlb_id": "135", "name": "San Diego Padres", "abbr": "SD", "league": "NL", "div": "West", "venue": "2680"},
    {"mlb_id": "137", "name": "San Francisco Giants", "abbr": "SF", "league": "NL", "div": "West", "venue": "2395"},
    {"mlb_id": "136", "name": "Seattle Mariners", "abbr": "SEA", "league": "AL", "div": "West", "venue": "680"},
    {"mlb_id": "138", "name": "St. Louis Cardinals", "abbr": "STL", "league": "NL", "div": "Central", "venue": "2889"},
    {"mlb_id": "139", "name": "Tampa Bay Rays", "abbr": "TB", "league": "AL", "div": "East", "venue": "12"},
    {"mlb_id": "140", "name": "Texas Rangers", "abbr": "TEX", "league": "AL", "div": "West", "venue": "13"},
    {"mlb_id": "141", "name": "Toronto Blue Jays", "abbr": "TOR", "league": "AL", "div": "East", "venue": "14"},
    {"mlb_id": "120", "name": "Washington Nationals", "abbr": "WSH", "league": "NL", "div": "East", "venue": "3309"},
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        # Build stadium lookup so we can link teams
        stadium_map: dict[str, uuid.UUID] = {}

        from app.services.park_data import PARKS_BY_VENUE_ID

        for s in STADIUMS:
            sid = uuid.uuid4()
            stadium_map[s["mlb_venue_id"]] = sid
            park = PARKS_BY_VENUE_ID.get(s["mlb_venue_id"], {})
            dims = park.get("dimensions", [s["lf"], None, s["cf"], None, s["rf"]])
            heights = park.get("wall_heights") or {}
            session.add(Stadium(
                id=sid,
                mlb_venue_id=s["mlb_venue_id"],
                name=park.get("name", s["name"]),
                city=s["city"],
                state=s["state"],
                latitude=s["lat"],
                longitude=s["lon"],
                altitude_ft=s["alt"],
                roof_type=park.get("roof", s["roof"]),
                surface=park.get("surface", s["surface"]),
                left_line_ft=dims[0],
                left_center_ft=dims[1],
                center_ft=dims[2],
                right_center_ft=dims[3],
                right_line_ft=dims[4],
                left_wall_ht=heights.get("left_field"),
                right_wall_ht=heights.get("right_field"),
                wall_heights=park.get("wall_heights"),
                features=park.get("features", []),
            ))

        await session.flush()

        for t in TEAMS:
            session.add(Team(
                id=uuid.uuid4(),
                mlb_team_id=t["mlb_id"],
                name=t["name"],
                abbreviation=t["abbr"],
                league=t["league"],
                division=t["div"],
                home_stadium_id=stadium_map.get(t["venue"]),
            ))

        await session.commit()
        print(f"Seeded {len(STADIUMS)} stadiums and {len(TEAMS)} teams.")


if __name__ == "__main__":
    asyncio.run(seed())
