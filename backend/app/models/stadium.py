from sqlalchemy import Float, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Stadium(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "stadium"

    mlb_venue_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(50), nullable=False)
    state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    country: Mapped[str] = mapped_column(String(50), default="USA", nullable=False)

    # Geography — affects ball flight (altitude) and positioning (outfield size)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude_ft: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Field characteristics
    roof_type: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    surface: Mapped[str] = mapped_column(String(10), default="grass", nullable=False)
    outfield_acres: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Wall distances (feet)
    left_line_ft: Mapped[float | None] = mapped_column(Float, nullable=True)
    left_center_ft: Mapped[float | None] = mapped_column(Float, nullable=True)
    center_ft: Mapped[float | None] = mapped_column(Float, nullable=True)
    right_center_ft: Mapped[float | None] = mapped_column(Float, nullable=True)
    right_line_ft: Mapped[float | None] = mapped_column(Float, nullable=True)
    left_wall_ht: Mapped[float | None] = mapped_column(Float, nullable=True)
    right_wall_ht: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Park geometry extras — wall heights per segment, venue feature notes
    wall_heights: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    features: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Park factors (from FanGraphs)
    park_factor_runs: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    park_factor_hr: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)

    def __repr__(self) -> str:
        return f"<Stadium {self.name}>"
