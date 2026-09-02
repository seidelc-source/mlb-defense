// src/api/alignmentApi.ts
import { apiClient } from './client'
import type {
  AlignmentHistoryItem,
  AlignmentRequest,
  AlignmentResponse,
  AlignmentScoreRequest,
  AlignmentScoreResponse,
  GameWeather,
  StadiumLayout,
  StadiumResponse,
  TeamSummary,
  PlayerSummary,
  WeatherEffect,
  WeatherInput,
} from '@/types'

export const alignmentApi = {
  recommend: async (req: AlignmentRequest): Promise<AlignmentResponse> => {
    const { data } = await apiClient.post('/alignments/recommend', req)
    return data
  },

  score: async (req: AlignmentScoreRequest): Promise<AlignmentScoreResponse> => {
    const { data } = await apiClient.post('/alignments/score', req)
    return data
  },

  get: async (alignmentId: string): Promise<AlignmentResponse> => {
    const { data } = await apiClient.get(`/alignments/${alignmentId}`)
    return data
  },

  getHistory: async (params?: {
    batter_id?: string
    pitcher_id?: string
    team_id?: string
    limit?: number
  }): Promise<AlignmentHistoryItem[]> => {
    const { data } = await apiClient.get('/alignments', { params })
    return data
  },
}

export const teamApi = {
  list: async (): Promise<TeamSummary[]> => {
    const { data } = await apiClient.get('/teams')
    return data
  },

  roster: async (teamId: string): Promise<PlayerSummary[]> => {
    const { data } = await apiClient.get(`/teams/${teamId}/roster`)
    return data
  },
}

export const stadiumApi = {
  list: async (): Promise<StadiumResponse[]> => {
    const { data } = await apiClient.get('/stadiums')
    return data
  },

  layout: async (stadiumId: string): Promise<StadiumLayout> => {
    const { data } = await apiClient.get(`/stadiums/${stadiumId}/layout`)
    return data
  },
}

export const weatherApi = {
  current: async (stadiumId: string): Promise<GameWeather | null> => {
    const { data } = await apiClient.get(`/weather/current/${stadiumId}`)
    return data
  },

  preview: async (input: WeatherInput, stadiumId?: string): Promise<WeatherEffect> => {
    const { data } = await apiClient.post('/weather/preview', input, {
      params: stadiumId ? { stadium_id: stadiumId } : undefined,
    })
    return data
  },
}
