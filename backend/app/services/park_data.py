"""
Curated park geometry — public five-point wall dimensions, notable wall
heights, and venue features for all 30 MLB parks.

Keyed by MLB venue id (Stadium.mlb_venue_id). Dimensions are
[LF line, LF-center, CF, RF-center, RF line] in feet.

These are realistic app visuals from public dimension references, not
surveyed CAD or Hawk-Eye data — appropriate for positioning context,
not wall-contact catch probability.
"""
from __future__ import annotations

from typing import Any, TypedDict


class ParkInfo(TypedDict, total=False):
    name: str
    dimensions: list[int]              # [lf, lc, cf, rc, rf]
    wall_heights: dict[str, float]     # segment key -> feet
    features: list[str]
    roof: str
    surface: str
    city: str
    state: str
    lat: float
    lon: float
    alt: float


DIMENSION_KEYS = ["left_field", "left_center", "center_field", "right_center", "right_field"]

PARKS_BY_VENUE_ID: dict[str, ParkInfo] = {
    "15": {"name": "Chase Field", "dimensions": [330, 374, 407, 374, 335],
           "features": ["Retractable roof", "Deep center"], "roof": "retractable", "surface": "synthetic"},
    "4705": {"name": "Truist Park", "dimensions": [335, 385, 400, 375, 325],
             "features": ["Asymmetric power alleys"], "roof": "open", "surface": "grass"},
    "2": {"name": "Oriole Park at Camden Yards", "dimensions": [333, 384, 400, 373, 318],
          "features": ["Tall left-field wall", "Short right-field line"], "roof": "open", "surface": "grass"},
    "3": {"name": "Fenway Park", "dimensions": [310, 379, 420, 380, 302],
          "wall_heights": {"left_field": 37.2, "right_field": 3.0},
          "features": ["Green Monster", "Deep center triangle", "Pesky's Pole"], "roof": "open", "surface": "grass"},
    "17": {"name": "Wrigley Field", "dimensions": [355, 368, 400, 368, 353],
           "features": ["Deep corners", "Ivy-covered brick wall"], "roof": "open", "surface": "grass"},
    "4": {"name": "Rate Field", "dimensions": [330, 375, 400, 375, 335],
          "features": ["Symmetric power alleys"], "roof": "open", "surface": "grass"},
    "2602": {"name": "Great American Ball Park", "dimensions": [328, 379, 404, 370, 325],
             "features": ["Short right-field line"], "roof": "open", "surface": "grass"},
    "5": {"name": "Progressive Field", "dimensions": [325, 370, 405, 375, 325],
          "features": ["Balanced alleys", "Tall left-field wall"], "roof": "open", "surface": "grass"},
    "19": {"name": "Coors Field", "dimensions": [347, 390, 415, 375, 350],
           "features": ["Largest outfield in MLB", "High-altitude run environment"], "roof": "open", "surface": "grass"},
    "2394": {"name": "Comerica Park", "dimensions": [345, 370, 412, 365, 330],
             "features": ["Deep center field"], "roof": "open", "surface": "grass"},
    "2392": {"name": "Daikin Park", "dimensions": [315, 362, 409, 373, 326],
             "wall_heights": {"left_field": 19.0, "left_center": 25.0},
             "features": ["Crawford Boxes", "Deep center notch", "Retractable roof"],
             "roof": "retractable", "surface": "grass"},
    "7": {"name": "Kauffman Stadium", "dimensions": [330, 387, 410, 387, 330],
          "features": ["Symmetric deep alleys"], "roof": "open", "surface": "grass"},
    "1": {"name": "Angel Stadium", "dimensions": [347, 390, 396, 370, 350],
          "features": ["Deep corners", "Right-center power alley"], "roof": "open", "surface": "grass"},
    "22": {"name": "Dodger Stadium", "dimensions": [330, 375, 395, 375, 330],
           "features": ["Classic balanced bowl"], "roof": "open", "surface": "grass"},
    "4169": {"name": "loanDepot park", "dimensions": [344, 386, 407, 392, 335],
             "features": ["Retractable roof", "Large alleys"], "roof": "retractable", "surface": "synthetic"},
    "32": {"name": "American Family Field", "dimensions": [344, 371, 400, 374, 345],
           "features": ["Retractable roof", "Balanced corners"], "roof": "retractable", "surface": "grass"},
    "3312": {"name": "Target Field", "dimensions": [339, 377, 411, 365, 328],
             "features": ["Deep center-left", "Short right-field porch"], "roof": "open", "surface": "grass"},
    "3289": {"name": "Citi Field", "dimensions": [335, 358, 408, 375, 330],
             "features": ["Irregular left-center wall", "Deep center"], "roof": "open", "surface": "grass"},
    "3313": {"name": "Yankee Stadium", "dimensions": [318, 399, 408, 385, 314],
             "features": ["Short right-field porch", "Deep left-center"], "roof": "open", "surface": "grass"},
    "2529": {"name": "Sutter Health Park", "dimensions": [330, 380, 403, 380, 325],
             "features": ["Temporary MLB home", "Compact right-field corner"],
             "roof": "open", "surface": "grass",
             "city": "West Sacramento", "state": "CA", "lat": 38.5803, "lon": -121.5133, "alt": 20},
    "2681": {"name": "Citizens Bank Park", "dimensions": [329, 374, 401, 369, 330],
             "features": ["Compact power alleys"], "roof": "open", "surface": "grass"},
    "31": {"name": "PNC Park", "dimensions": [325, 389, 399, 375, 320],
           "wall_heights": {"right_field": 21.0},
           "features": ["Clemente Wall", "Short right-field line"], "roof": "open", "surface": "grass"},
    "2680": {"name": "Petco Park", "dimensions": [336, 390, 396, 391, 322],
             "features": ["Western Metal Supply corner", "Deep alleys"], "roof": "open", "surface": "grass"},
    "2395": {"name": "Oracle Park", "dimensions": [339, 399, 391, 415, 309],
             "wall_heights": {"right_field": 24.0},
             "features": ["Triples Alley", "Short right-field arcade"], "roof": "open", "surface": "grass"},
    "680": {"name": "T-Mobile Park", "dimensions": [331, 378, 401, 381, 326],
            "features": ["Retractable roof", "Deep right-center"], "roof": "retractable", "surface": "grass"},
    "2889": {"name": "Busch Stadium", "dimensions": [336, 375, 400, 375, 335],
             "features": ["Balanced modern outfield"], "roof": "open", "surface": "grass"},
    "12": {"name": "Tropicana Field", "dimensions": [315, 370, 404, 370, 322],
           "features": ["Fixed roof", "Compact corners"], "roof": "dome", "surface": "synthetic"},
    "13": {"name": "Globe Life Field", "dimensions": [329, 372, 407, 374, 326],
           "features": ["Retractable roof", "Deep center"], "roof": "retractable", "surface": "synthetic"},
    "14": {"name": "Rogers Centre", "dimensions": [328, 375, 400, 375, 328],
           "features": ["Retractable roof", "Symmetric corners"], "roof": "retractable", "surface": "synthetic"},
    "3309": {"name": "Nationals Park", "dimensions": [336, 377, 402, 370, 335],
             "features": ["Left-center notch", "Balanced right field"], "roof": "open", "surface": "grass"},
}

# The Athletics moved from Oakland Coliseum (venue 10) to Sutter Health Park
# (venue 2529) in 2025 — enrichment migrates the old row in place.
VENUE_MIGRATIONS: dict[str, str] = {"10": "2529"}

GENERIC_DIMENSIONS = [330, 375, 400, 375, 330]


def dimension_map(values: list[int | float]) -> dict[str, int]:
    return {key: int(values[i]) for i, key in enumerate(DIMENSION_KEYS)}


def park_info(mlb_venue_id: str) -> ParkInfo | None:
    return PARKS_BY_VENUE_ID.get(mlb_venue_id)
