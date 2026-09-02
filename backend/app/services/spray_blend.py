"""
Shared spray-zone blending.

Merges per-season ``BatterSprayProfile`` zone rows into a single career
aggregate, optionally weighting recent seasons more heavily. Used by both the
spray-chart endpoint (season=0 "Total") and the alignment engine, so a
recommendation positions fielders using the same recency-aware tendencies the
spray UI shows.
"""
from __future__ import annotations

from types import SimpleNamespace

ZONE_RATIO_FIELDS = (
    "groundball_pct", "flyball_pct", "linedrive_pct", "popup_pct",
    "single_pct", "double_pct", "triple_pct", "hr_pct", "error_pct",
)


def merge_zone_rows(rows, recency_decay: float = 1.0):
    """Merge per-season zone rows into career totals.

    Counts (hit_count/out_count/total/sample_n) stay honest raw sums so the
    reported sample size and data-sufficiency checks reflect reality. Rate
    fields are weighted averages where each season's contribution is scaled by
    ``recency_decay ** (latest_season - season)``, so recent tendencies
    dominate the blend. ``recency_decay = 1.0`` reduces exactly to a plain
    sample-weighted average.
    """
    latest = max((r.season for r in rows), default=0)
    rate_fields = ("hit_pct", "out_pct", *ZONE_RATIO_FIELDS)

    by_zone: dict[int, dict] = {}
    for r in rows:
        weighted_n = r.total_batted_balls * (recency_decay ** (latest - r.season))
        acc = by_zone.setdefault(r.fielding_zone, {
            "hits": 0, "outs": 0, "total": 0, "weighted_n": 0.0,
            **{f: 0.0 for f in rate_fields},
        })
        acc["hits"] += r.hit_count
        acc["outs"] += r.out_count
        acc["total"] += r.total_batted_balls
        acc["weighted_n"] += weighted_n
        for f in rate_fields:
            acc[f] += getattr(r, f) * weighted_n

    merged = []
    for zone, acc in sorted(by_zone.items()):
        wn = acc["weighted_n"] or 1.0
        merged.append(SimpleNamespace(
            fielding_zone=zone,
            hit_count=acc["hits"],
            out_count=acc["outs"],
            total_batted_balls=acc["total"],
            sample_n=acc["total"],
            **{f: acc[f] / wn for f in rate_fields},
        ))
    return merged
