"""Add catcher-specific metric columns to fielding_profile.

Revision ID: 002_catcher_metrics
Revises: 001_initial
Create Date: 2026-06-10
"""
import sqlalchemy as sa
from alembic import op

revision = "002_catcher_metrics"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fielding_profile", sa.Column("framing_runs", sa.Float(), nullable=True))
    op.add_column("fielding_profile", sa.Column("blocking_runs", sa.Float(), nullable=True))
    op.add_column("fielding_profile", sa.Column("catcher_throwing_runs", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("fielding_profile", "catcher_throwing_runs")
    op.drop_column("fielding_profile", "blocking_runs")
    op.drop_column("fielding_profile", "framing_runs")
