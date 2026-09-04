"""Add per-opportunity success-rate columns to fielding_profile.

The Savant OAA leaderboard provides actual / positioning-adjusted-estimated
success rates whose difference is OAA per opportunity — the playing-time-
standardized fielding-skill rate. The ingest previously dropped them (and the
leaderboard has no innings/games/attempts, which is why those columns are 0
for every row — see documentation/DATA_KNOWLEDGE.md 2026-09-04). Nullable;
backfill via `python -m scripts.ingest_all --fielding-only --season <Y>`.

Revision ID: 006_fielding_success_rates
Revises: 005_fielding_alignment
Create Date: 2026-09-04
"""
import sqlalchemy as sa
from alembic import op

revision = "006_fielding_success_rates"
down_revision = "005_fielding_alignment"
branch_labels = None
depends_on = None

COLUMNS = ("actual_success_rate", "estimated_success_rate", "diff_success_rate")


def upgrade() -> None:
    for name in COLUMNS:
        op.add_column("fielding_profile", sa.Column(name, sa.Float(), nullable=True))


def downgrade() -> None:
    for name in COLUMNS:
        op.drop_column("fielding_profile", name)
