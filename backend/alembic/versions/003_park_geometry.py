"""Add park geometry columns (wall_heights, features) to stadium.

Revision ID: 003_park_geometry
Revises: 002_catcher_metrics
Create Date: 2026-06-11
"""
import sqlalchemy as sa
from alembic import op

revision = "003_park_geometry"
down_revision = "002_catcher_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stadium", sa.Column("wall_heights", sa.JSON(), nullable=True))
    op.add_column("stadium", sa.Column("features", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("stadium", "features")
    op.drop_column("stadium", "wall_heights")
