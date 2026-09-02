"""Sync pitcher_profile with the fleshed-out model: add tendency/velocity
columns used by the alignment engine, drop the unused games/innings columns.

Revision ID: 004_pitcher_profile_metrics
Revises: 003_park_geometry
Create Date: 2026-06-21
"""
import sqlalchemy as sa
from alembic import op

revision = "004_pitcher_profile_metrics"
down_revision = "003_park_geometry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NOT NULL string columns get a temporary server_default so the ADD succeeds
    # on any existing rows; the model carries no server default, so drop it after.
    op.add_column("pitcher_profile", sa.Column("role", sa.String(3), nullable=False, server_default="RP"))
    op.add_column("pitcher_profile", sa.Column("pitcher_type", sa.String(20), nullable=False, server_default="neutral"))
    op.alter_column("pitcher_profile", "role", server_default=None)
    op.alter_column("pitcher_profile", "pitcher_type", server_default=None)

    op.add_column("pitcher_profile", sa.Column("linedrive_pct", sa.Float(), nullable=True))
    op.add_column("pitcher_profile", sa.Column("popup_pct", sa.Float(), nullable=True))
    op.add_column("pitcher_profile", sa.Column("avg_fastball_mph", sa.Float(), nullable=True))
    op.add_column("pitcher_profile", sa.Column("max_fastball_mph", sa.Float(), nullable=True))
    op.add_column("pitcher_profile", sa.Column("avg_velocity_mph", sa.Float(), nullable=True))
    op.add_column("pitcher_profile", sa.Column("spin_rate_avg", sa.Integer(), nullable=True))

    # Replaced / no longer modeled
    op.drop_column("pitcher_profile", "avg_velocity")  # → avg_velocity_mph
    op.drop_column("pitcher_profile", "games")
    op.drop_column("pitcher_profile", "innings_pitched")


def downgrade() -> None:
    op.add_column("pitcher_profile", sa.Column("innings_pitched", sa.Float(), server_default="0"))
    op.add_column("pitcher_profile", sa.Column("games", sa.Integer(), server_default="0"))
    op.add_column("pitcher_profile", sa.Column("avg_velocity", sa.Float(), nullable=True))

    op.drop_column("pitcher_profile", "spin_rate_avg")
    op.drop_column("pitcher_profile", "avg_velocity_mph")
    op.drop_column("pitcher_profile", "max_fastball_mph")
    op.drop_column("pitcher_profile", "avg_fastball_mph")
    op.drop_column("pitcher_profile", "popup_pct")
    op.drop_column("pitcher_profile", "linedrive_pct")
    op.drop_column("pitcher_profile", "pitcher_type")
    op.drop_column("pitcher_profile", "role")
