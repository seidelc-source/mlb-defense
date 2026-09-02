"""Initial schema — all tables.

Revision ID: 001_initial
Revises:
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mlb_team_id", sa.String(10), unique=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("abbreviation", sa.String(5), nullable=False, index=True),
        sa.Column("league", sa.String(2), nullable=False),
        sa.Column("division", sa.String(10), nullable=False),
        sa.Column("home_stadium_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "stadium",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mlb_venue_id", sa.String(20), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("city", sa.String(50), nullable=False),
        sa.Column("state", sa.String(50), nullable=True),
        sa.Column("country", sa.String(50), nullable=False, server_default="USA"),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("altitude_ft", sa.Float, nullable=False, server_default="0"),
        sa.Column("roof_type", sa.String(20), nullable=False, server_default="open"),
        sa.Column("surface", sa.String(10), nullable=False, server_default="grass"),
        sa.Column("outfield_acres", sa.Float, nullable=True),
        sa.Column("left_line_ft", sa.Float, nullable=True),
        sa.Column("left_center_ft", sa.Float, nullable=True),
        sa.Column("center_ft", sa.Float, nullable=True),
        sa.Column("right_center_ft", sa.Float, nullable=True),
        sa.Column("right_line_ft", sa.Float, nullable=True),
        sa.Column("left_wall_ht", sa.Float, nullable=True),
        sa.Column("right_wall_ht", sa.Float, nullable=True),
        sa.Column("park_factor_runs", sa.Float, nullable=False, server_default="100"),
        sa.Column("park_factor_hr", sa.Float, nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "player",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mlbam_id", sa.String(20), unique=True, nullable=True, index=True),
        sa.Column("fangraphs_id", sa.String(20), unique=True, nullable=True),
        sa.Column("bbref_id", sa.String(20), unique=True, nullable=True),
        sa.Column("lahman_id", sa.String(20), nullable=True),
        sa.Column("full_name", sa.String(100), nullable=False, index=True),
        sa.Column("first_name", sa.String(50), nullable=False),
        sa.Column("last_name", sa.String(50), nullable=False, index=True),
        sa.Column("position", sa.String(5), nullable=False, index=True),
        sa.Column("throws", sa.String(1), nullable=False),
        sa.Column("bats", sa.String(1), nullable=False),
        sa.Column("birth_date", sa.Date, nullable=True),
        sa.Column("birth_country", sa.String(50), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("pro_debut", sa.Date, nullable=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("team.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "fielding_profile",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("player.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("season", sa.Integer, nullable=False),
        sa.Column("position", sa.String(5), nullable=False),
        sa.Column("games", sa.Integer, server_default="0"),
        sa.Column("innings", sa.Float, server_default="0"),
        sa.Column("sprint_speed_ft_s", sa.Float, nullable=True),
        sa.Column("sprint_speed_level", sa.Integer, nullable=True),
        sa.Column("range_pct_vs_avg", sa.Float, nullable=True),
        sa.Column("range_level", sa.Integer, nullable=True),
        sa.Column("reaction_time_s", sa.Float, nullable=True),
        sa.Column("reaction_time_level", sa.Integer, nullable=True),
        sa.Column("route_efficiency_pct", sa.Float, nullable=True),
        sa.Column("route_efficiency_level", sa.Integer, nullable=True),
        sa.Column("arm_strength_mph", sa.Float, nullable=True),
        sa.Column("arm_strength_level", sa.Integer, nullable=True),
        sa.Column("arm_accuracy_pct", sa.Float, nullable=True),
        sa.Column("arm_accuracy_level", sa.Integer, nullable=True),
        sa.Column("outs_above_average", sa.Float, nullable=True),
        sa.Column("oaa_back", sa.Float, nullable=True),
        sa.Column("oaa_in", sa.Float, nullable=True),
        sa.Column("oaa_left", sa.Float, nullable=True),
        sa.Column("oaa_right", sa.Float, nullable=True),
        sa.Column("fielding_run_value", sa.Float, nullable=True),
        sa.Column("fielder_throwing_runs", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_fielding_player_season", "fielding_profile", ["player_id", "season"])

    op.create_table(
        "pitcher_profile",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("player.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("season", sa.Integer, nullable=False),
        sa.Column("games", sa.Integer, server_default="0"),
        sa.Column("innings_pitched", sa.Float, server_default="0"),
        sa.Column("groundball_pct", sa.Float, nullable=True),
        sa.Column("flyball_pct", sa.Float, nullable=True),
        sa.Column("strikeout_pct", sa.Float, nullable=True),
        sa.Column("walk_pct", sa.Float, nullable=True),
        sa.Column("avg_velocity", sa.Float, nullable=True),
        sa.Column("pitch_mix", postgresql.JSON, nullable=True),
        sa.Column("xfip", sa.Float, nullable=True),
        sa.Column("siera", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pitcher_player_season", "pitcher_profile", ["player_id", "season"])

    op.create_table(
        "pitch_appearance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mlb_play_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("game_id", sa.String(20), nullable=False, index=True),
        sa.Column("game_date", sa.Date, nullable=False),
        sa.Column("season", sa.Integer, nullable=False),
        sa.Column("inning", sa.Integer, nullable=False),
        sa.Column("inning_half", sa.String(6), nullable=False),
        sa.Column("pitcher_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("player.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("batter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("player.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("stadium_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stadium.id", ondelete="SET NULL"), nullable=True),
        sa.Column("home_team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("away_team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pitch_type", sa.String(5), nullable=True, index=True),
        sa.Column("pitch_type_label", sa.String(30), nullable=True),
        sa.Column("release_speed_mph", sa.Float, nullable=True),
        sa.Column("release_speed_level", sa.Integer, nullable=True),
        sa.Column("spin_rate", sa.Integer, nullable=True),
        sa.Column("pfx_x", sa.Float, nullable=True),
        sa.Column("pfx_z", sa.Float, nullable=True),
        sa.Column("plate_x", sa.Float, nullable=True),
        sa.Column("plate_z", sa.Float, nullable=True),
        sa.Column("zone", sa.Integer, nullable=True),
        sa.Column("balls", sa.Integer, server_default="0"),
        sa.Column("strikes", sa.Integer, server_default="0"),
        sa.Column("outs_when_up", sa.Integer, server_default="0"),
        sa.Column("on_1b", sa.Boolean, server_default="false"),
        sa.Column("on_2b", sa.Boolean, server_default="false"),
        sa.Column("on_3b", sa.Boolean, server_default="false"),
        sa.Column("events", sa.String(30), nullable=True, index=True),
        sa.Column("description", sa.String(50), nullable=True),
        sa.Column("bb_type", sa.String(20), nullable=True),
        sa.Column("launch_angle", sa.Float, nullable=True),
        sa.Column("launch_speed", sa.Float, nullable=True),
        sa.Column("hit_distance_sc", sa.Float, nullable=True),
        sa.Column("hc_x", sa.Float, nullable=True),
        sa.Column("hc_y", sa.Float, nullable=True),
        sa.Column("fielding_zone", sa.Integer, nullable=True),
        sa.Column("general_result", sa.String(5), nullable=True),
        sa.Column("specific_result", sa.String(10), nullable=True),
        sa.Column("ball_trajectory", sa.String(15), nullable=True),
        sa.Column("fielder_positions", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pitch_batter_season", "pitch_appearance", ["batter_id", "season"])
    op.create_index("ix_pitch_pitcher_season", "pitch_appearance", ["pitcher_id", "season"])
    op.create_index("ix_pitch_game_date", "pitch_appearance", ["game_date"])

    op.create_table(
        "game_weather",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("game_id", sa.String(20), nullable=False, index=True),
        sa.Column("stadium_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stadium.id", ondelete="SET NULL"), nullable=True),
        sa.Column("game_date", sa.Date, nullable=False),
        sa.Column("game_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_pitch_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("temperature_f", sa.Float, nullable=True),
        sa.Column("humidity_pct", sa.Float, nullable=True),
        sa.Column("wind_speed_mph", sa.Float, nullable=True),
        sa.Column("wind_direction_deg", sa.Float, nullable=True),
        sa.Column("wind_direction_label", sa.String(3), nullable=True),
        sa.Column("wind_speed_level", sa.Integer, nullable=True),
        sa.Column("pressure_mb", sa.Float, nullable=True),
        sa.Column("conditions", sa.String(30), nullable=True),
        sa.Column("wind_x_component", sa.Float, nullable=True),
        sa.Column("wind_y_component", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "batter_spray_profile",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("player.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("season", sa.Integer, nullable=False),
        sa.Column("pitch_type", sa.String(5), nullable=True),
        sa.Column("pitcher_hand", sa.String(1), nullable=True),
        sa.Column("pitch_speed_min", sa.Float, nullable=True),
        sa.Column("pitch_speed_max", sa.Float, nullable=True),
        sa.Column("count_state", sa.String(10), nullable=True),
        sa.Column("fielding_zone", sa.Integer, nullable=False),
        sa.Column("hit_count", sa.Integer, server_default="0"),
        sa.Column("out_count", sa.Integer, server_default="0"),
        sa.Column("total_batted_balls", sa.Integer, server_default="0"),
        sa.Column("hit_pct", sa.Float, server_default="0"),
        sa.Column("out_pct", sa.Float, server_default="0"),
        sa.Column("groundball_pct", sa.Float, server_default="0"),
        sa.Column("flyball_pct", sa.Float, server_default="0"),
        sa.Column("linedrive_pct", sa.Float, server_default="0"),
        sa.Column("popup_pct", sa.Float, server_default="0"),
        sa.Column("single_pct", sa.Float, server_default="0"),
        sa.Column("double_pct", sa.Float, server_default="0"),
        sa.Column("triple_pct", sa.Float, server_default="0"),
        sa.Column("hr_pct", sa.Float, server_default="0"),
        sa.Column("error_pct", sa.Float, server_default="0"),
        sa.Column("sample_n", sa.Integer, server_default="0"),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_spray_player_season_scenario", "batter_spray_profile", ["player_id", "season", "pitch_type", "pitcher_hand"])

    op.create_table(
        "defensive_alignment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("alignment_type", sa.String(20), nullable=False, server_default="recommendation"),
        sa.Column("game_id", sa.String(20), nullable=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("team.id", ondelete="SET NULL"), nullable=True),
        sa.Column("batter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("player.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("pitcher_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("player.id", ondelete="SET NULL"), nullable=True),
        sa.Column("stadium_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stadium.id", ondelete="SET NULL"), nullable=True),
        sa.Column("weather_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("game_weather.id", ondelete="SET NULL"), nullable=True),
        sa.Column("inning", sa.Integer, nullable=True),
        sa.Column("outs", sa.Integer, nullable=True),
        sa.Column("on_1b", sa.Boolean, server_default="false"),
        sa.Column("on_2b", sa.Boolean, server_default="false"),
        sa.Column("on_3b", sa.Boolean, server_default="false"),
        sa.Column("score_diff", sa.Integer, nullable=True),
        sa.Column("shift_type", sa.String(20), nullable=False, server_default="standard"),
        sa.Column("fielder_positions", postgresql.JSON, nullable=True),
        sa.Column("predicted_oaa_delta", sa.Float, nullable=True),
        sa.Column("predicted_hit_pct", sa.Float, nullable=True),
        sa.Column("predicted_out_pct", sa.Float, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("factors_used", postgresql.JSON, nullable=True),
        sa.Column("optimize_for", sa.String(25), nullable=False, server_default="balanced"),
        sa.Column("model_version", sa.String(20), nullable=False, server_default="0.1.0"),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_alignment_batter_pitcher", "defensive_alignment", ["batter_id", "pitcher_id"])

    op.create_table(
        "player_injury",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("player.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("body_part", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("expected_return", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("speed_factor", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("arm_strength_factor", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("arm_accuracy_factor", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("reaction_factor", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("range_factor", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_injury_player_active", "player_injury", ["player_id", "active"])


def downgrade() -> None:
    op.drop_table("player_injury")
    op.drop_table("defensive_alignment")
    op.drop_table("batter_spray_profile")
    op.drop_table("game_weather")
    op.drop_table("pitch_appearance")
    op.drop_table("pitcher_profile")
    op.drop_table("fielding_profile")
    op.drop_table("player")
    op.drop_table("stadium")
    op.drop_table("team")
