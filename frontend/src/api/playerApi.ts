// src/api/playerApi.ts
import { apiClient } from './client'
import type {
  FieldingProfile,
  InjuryCreate,
  InjuryResponse,
  PitcherProfile,
  PlayerDetail,
  PlayerRangeResponse,
  PlayerSummary,
  SprayChartResponse,
} from '@/types'

export interface PlayerListResponse {
  total: number
  players: PlayerSummary[]
}

export interface PlayerSearchParams {
  name?: string
  position?: string
  active?: boolean
  team_id?: string
  role?: 'batter' | 'pitcher'
  offset?: number
  limit?: number
}

export interface SprayParams {
  season?: number
  pitch_type?: string
  pitcher_hand?: string
  speed_min?: number
  speed_max?: number
}

export const playerApi = {
  list: async (params?: PlayerSearchParams): Promise<PlayerListResponse> => {
    const { data } = await apiClient.get('/players', { params })
    return data
  },

  get: async (playerId: string): Promise<PlayerDetail> => {
    const { data } = await apiClient.get(`/players/${playerId}`)
    return data
  },

  getFielding: async (
    playerId: string,
    season = 2024,
    position?: string,
    applyInjuries = true
  ): Promise<FieldingProfile[]> => {
    const { data } = await apiClient.get(`/players/${playerId}/fielding`, {
      params: { season, position, apply_injuries: applyInjuries },
    })
    return data
  },

  getSpray: async (playerId: string, params?: SprayParams): Promise<SprayChartResponse> => {
    const { data } = await apiClient.get(`/spray/${playerId}`, { params })
    return data
  },

  getSpraySeasons: async (playerId: string): Promise<number[]> => {
    const { data } = await apiClient.get(`/spray/${playerId}/seasons`)
    return data
  },

  getFieldingSeasons: async (playerId: string): Promise<number[]> => {
    const { data } = await apiClient.get(`/players/${playerId}/fielding/seasons`)
    return data
  },

  getPitching: async (playerId: string, season = 2024): Promise<PitcherProfile> => {
    const { data } = await apiClient.get(`/players/${playerId}/pitching`, {
      params: { season },
    })
    return data
  },

  getPitchingSeasons: async (playerId: string): Promise<number[]> => {
    const { data } = await apiClient.get(`/players/${playerId}/pitching/seasons`)
    return data
  },

  getRange: async (
    playerId: string,
    position?: string,
    season = 2024,
    injuryActive = true
  ): Promise<PlayerRangeResponse> => {
    const { data } = await apiClient.get(`/range/${playerId}`, {
      params: { position, season, injury_active: injuryActive },
    })
    return data
  },

  getInjuries: async (playerId: string): Promise<InjuryResponse[]> => {
    const { data } = await apiClient.get(`/players/${playerId}/injury`)
    return data
  },

  addInjury: async (playerId: string, body: InjuryCreate): Promise<InjuryResponse> => {
    const { data } = await apiClient.post(`/players/${playerId}/injury`, body)
    return data
  },

  endInjury: async (playerId: string, injuryId: string): Promise<InjuryResponse> => {
    const { data } = await apiClient.put(`/players/${playerId}/injury/${injuryId}/end`)
    return data
  },
}
