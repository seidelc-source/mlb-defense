// src/types/index.ts — all shared types

export interface PlayerSummary {
  id: string
  full_name: string
  position: string
  throws: string
  bats: string
  team_id: string | null
  active: boolean
}

export interface PlayerDetail extends PlayerSummary {
  mlbam_id: string | null
  fangraphs_id: string | null
  bbref_id: string | null
  first_name: string
  last_name: string
  birth_date: string | null
  birth_country: string | null
  pro_debut: string | null
}

export interface PitcherProfile {
  player: PlayerSummary
  season: number
  role: string          // SP | RP
  pitcher_type: string  // groundball | flyball | strikeout | neutral
  groundball_pct: number | null
  flyball_pct: number | null
  linedrive_pct: number | null
  popup_pct: number | null
  strikeout_pct: number | null
  walk_pct: number | null
  avg_velocity_mph: number | null
  avg_fastball_mph: number | null
  max_fastball_mph: number | null
  spin_rate_avg: number | null
  pitch_mix: Record<string, number> | null
}

export interface FieldingProfile {
  player: PlayerSummary
  season: number
  position: string
  games: number
  innings: number
  sprint_speed_ft_s: number | null
  sprint_speed_level: number | null
  range_pct_vs_avg: number | null
  range_level: number | null
  reaction_time_s: number | null
  reaction_time_level: number | null
  route_efficiency_pct: number | null
  route_efficiency_level: number | null
  arm_strength_mph: number | null
  arm_strength_level: number | null
  arm_accuracy_pct: number | null
  arm_accuracy_level: number | null
  outs_above_average: number | null
  oaa_back: number | null
  oaa_in: number | null
  oaa_left: number | null
  oaa_right: number | null
  fielding_run_value: number | null
  fielder_throwing_runs: number | null
  injury_adjusted: boolean
  injury_factors: InjuryFactors[] | null
}

export interface InjuryFactors {
  body_part: string
  severity: string
  speed_factor: number
  arm_strength_factor: number
  arm_accuracy_factor: number
  reaction_factor: number
  range_factor: number
}

export interface SprayZone {
  zone: number
  hit_pct: number
  out_pct: number
  trajectory: {
    groundball: number
    flyball: number
    linedrive: number
    popup: number
  }
  specific: {
    single: number
    double: number
    triple: number
    hr: number
    error: number
  }
  n: number
}

export interface SprayChartResponse {
  batter: PlayerSummary
  season: number
  filters_applied: Record<string, string | number | null>
  zones: SprayZone[]
  logistic_grid: number[][]
  sample_n: number
  weather_adjusted: boolean
  park_adjusted: boolean
  recency_weighted: boolean
}

export interface FielderPosition {
  player_id: string
  player_name: string
  x: number
  y: number
  depth_ft: number
  angle_deg: number
  catch_prob_zone: number
}

export interface AlignmentSummary {
  shift_type: string
  predicted_oaa_delta: number
  predicted_hit_pct: number
  confidence: number
}

export interface AlignmentResponse {
  alignment_id: string
  shift_type: string
  fielder_positions: Record<string, FielderPosition>
  coverage_map: number[][]
  overlap_zones: Array<Record<string, unknown>>
  predicted_oaa_delta: number
  predicted_hit_pct: number
  predicted_out_pct: number
  confidence: number
  optimize_for: string
  factors_applied: string[]
  alternatives: AlignmentSummary[]
  created_at: string
  pitcher_type?: string | null
  pitcher_groundball_pct?: number | null
  weather_carry?: number | null
}

export interface WeatherInput {
  temperature_f?: number | null
  humidity_pct?: number | null
  wind_speed_mph?: number | null
  wind_direction_deg?: number | null
  conditions?: string | null
}

export interface WeatherEffect {
  wind_x_component: number
  wind_y_component: number
  wind_direction_label: string | null
  wind_speed_level: number | null
  carry_factor: number
  carry_pct: number
  summary: string
}

export interface RosterEntry {
  player_id: string
  position: string
  injury_override?: Record<string, number>
}

export interface AlignmentRequest {
  team_id: string
  batter_id: string
  pitcher_id: string
  stadium_id: string
  weather_id?: string
  weather?: WeatherInput
  inning?: number
  outs?: number
  runners: { on_1b: boolean; on_2b: boolean; on_3b: boolean }
  score_diff?: number
  active_roster: RosterEntry[]
  optimize_for: 'prevent_hit' | 'prevent_extra_base' | 'balanced'
  include_factors: string[]
}

export interface PlayerRangeResponse {
  player_id: string
  player_name: string
  position: string
  center_x: number
  center_y: number
  radii: {
    zone_075s: number
    zone_125s: number
    zone_175s: number
    zone_225s: number
    zone_300s: number
  }
  arm_throw_range: {
    max_distance_ft: number
    accuracy_pct: number
  }
  effective_zones: number[]
  injury_adjusted: boolean
}

export interface GameWeather {
  id: string
  game_id: string
  stadium_id: string | null
  game_date: string
  temperature_f: number | null
  humidity_pct: number | null
  wind_speed_mph: number | null
  wind_direction_label: string | null
  wind_speed_level: number | null
  conditions: string | null
  wind_x_component: number | null
  wind_y_component: number | null
}

export interface StadiumResponse {
  id: string
  mlb_venue_id: string
  name: string
  city: string
  state: string | null
  altitude_ft: number
  roof_type: string
  surface: string
  outfield_acres: number | null
  left_line_ft: number | null
  center_ft: number | null
  right_line_ft: number | null
  park_factor_runs: number
  park_factor_hr: number
}

export interface IngestJobStatus {
  job_id: string
  status: 'pending' | 'running' | 'complete' | 'failed'
  source: string
  records_processed: number
  errors: string[]
  started_at: string
  finished_at: string | null
}

export interface TeamSummary {
  id: string
  name: string
  abbreviation: string
  league: string
  division: string
  home_stadium_id: string | null
}

export interface AlignmentScoreRequest {
  batter_id: string
  positions: Record<string, { x: number; y: number }>
  active_roster?: RosterEntry[]
  weather_id?: string
  stadium_id?: string
  season?: number
  optimize_for?: 'prevent_hit' | 'prevent_extra_base' | 'balanced'
}

export interface AlignmentScoreResponse {
  shift_type: string
  predicted_oaa_delta: number
  predicted_hit_pct: number
  predicted_out_pct: number
  confidence: number
  legal: boolean
  illegal_positions: string[]
}

export interface InjuryCreate {
  body_part: string
  severity: 'mild' | 'moderate' | 'severe'
  notes?: string
}

export interface InjuryResponse {
  id: string
  player_id: string
  body_part: string
  severity: string
  active: boolean
  start_date: string | null
  end_date: string | null
  speed_factor: number
  reaction_factor: number
  range_factor: number
  arm_strength_factor: number
  arm_accuracy_factor: number
  notes: string | null
}

export interface WallPoint {
  angle_deg: number
  distance_ft: number
  x: number
  y: number
}

export interface DistanceMarker {
  key: string
  label: string
  distance_ft: number
  x: number
  y: number
}

export interface FeatureWall {
  key: string
  height_ft: number
  label: string
}

export interface StadiumLayout {
  stadium_id: string
  name: string
  city: string
  state: string | null
  roof_type: string
  surface: string
  altitude_ft: number
  dimensions: Record<string, number>
  wall_points: WallPoint[]
  distance_markers: DistanceMarker[]
  feature_walls: FeatureWall[]
  features: string[]
  precision: string
}

export interface AlignmentHistoryItem {
  id: string
  shift_type: string
  batter_id: string | null
  pitcher_id: string | null
  inning: number | null
  outs: number | null
  fielder_positions: Record<string, [number, number]> | null
  predicted_oaa_delta: number | null
  predicted_hit_pct: number | null
  confidence: number | null
  optimize_for: string
  created_at: string
}
