"""Add Statcast fielder-alignment columns to pitch_appearance.

Captured from the raw Statcast pull (``if_fielding_alignment`` /
``of_fielding_alignment``) so the P0 evaluation harness can restrict to
batted balls fielded from a standard alignment. Both nullable — existing
rows stay NULL until backfilled (see scripts/backfill_alignment.py); the
engine does not consume these columns.

Revision ID: 005_fielding_alignment
Revises: 004_pitcher_profile_metrics
Create Date: 2026-09-02
"""
import sqlalchemy as sa
from alembic import op

revision = "005_fielding_alignment"
down_revision = "004_pitcher_profile_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pitch_appearance",
        sa.Column("if_fielding_alignment", sa.String(20), nullable=True),
    )
    op.add_column(
        "pitch_appearance",
        sa.Column("of_fielding_alignment", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pitch_appearance", "of_fielding_alignment")
    op.drop_column("pitch_appearance", "if_fielding_alignment")
