// src/stores/scenarioStore.ts
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

// localStorage when available (browser); silent in-memory fallback otherwise
// (tests, SSR).
function safeStorage(): Storage {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.getItem('__probe__')
      return window.localStorage
    }
  } catch {
    // fall through
  }
  const mem = new Map<string, string>()
  return {
    getItem: (k: string) => mem.get(k) ?? null,
    setItem: (k: string, v: string) => void mem.set(k, v),
    removeItem: (k: string) => void mem.delete(k),
    clear: () => mem.clear(),
    key: (i: number) => [...mem.keys()][i] ?? null,
    get length() {
      return mem.size
    },
  } as Storage
}

export interface Runners {
  on_1b: boolean
  on_2b: boolean
  on_3b: boolean
}

export interface WeatherSettings {
  enabled: boolean
  temperature_f: number
  wind_speed_mph: number
  wind_direction_deg: number
  humidity_pct: number
}

const defaultWeather: WeatherSettings = {
  enabled: false,
  temperature_f: 72,
  wind_speed_mph: 5,
  wind_direction_deg: 180, // blowing out to center
  humidity_pct: 50,
}

export interface ScenarioState {
  batterId: string | null
  pitcherId: string | null
  stadiumId: string | null
  teamId: string | null
  battingTeamId: string | null
  weatherId: string | null
  inning: number
  outs: number
  runners: Runners
  scoreDiff: number
  optimizeFor: 'prevent_hit' | 'prevent_extra_base' | 'balanced'
  activeRoster: Array<{ player_id: string; position: string }>
  weather: WeatherSettings

  setBatter: (id: string) => void
  setPitcher: (id: string) => void
  setStadium: (id: string) => void
  setTeam: (id: string) => void
  setBattingTeam: (id: string) => void
  setInning: (n: number) => void
  setOuts: (n: number) => void
  setRunners: (r: Partial<Runners>) => void
  setScoreDiff: (n: number) => void
  setOptimizeFor: (v: 'prevent_hit' | 'prevent_extra_base' | 'balanced') => void
  setRosterEntry: (position: string, playerId: string) => void
  setRoster: (entries: Array<{ player_id: string; position: string }>) => void
  setWeather: (partial: Partial<WeatherSettings>) => void
  reset: () => void
}

const defaultState = {
  batterId: null,
  pitcherId: null,
  stadiumId: null,
  teamId: null,
  battingTeamId: null,
  weatherId: null,
  inning: 1,
  outs: 0,
  runners: { on_1b: false, on_2b: false, on_3b: false },
  scoreDiff: 0,
  optimizeFor: 'balanced' as const,
  activeRoster: [],
  weather: defaultWeather,
}

export const useScenarioStore = create<ScenarioState>()(
  persist(
    (set) => ({
      ...defaultState,
      setBatter: (id) => set({ batterId: id }),
      setPitcher: (id) => set({ pitcherId: id }),
      setStadium: (id) => set({ stadiumId: id }),
      setTeam: (id) => set({ teamId: id }),
      setBattingTeam: (id) => set({ battingTeamId: id }),
      setInning: (n) => set({ inning: n }),
      setOuts: (n) => set({ outs: n }),
      setRunners: (r) =>
        set((s) => ({ runners: { ...s.runners, ...r } })),
      setScoreDiff: (n) => set({ scoreDiff: n }),
      setOptimizeFor: (v) => set({ optimizeFor: v }),
      setRosterEntry: (position, playerId) =>
        set((s) => {
          const roster = s.activeRoster.filter((e) => e.position !== position)
          return { activeRoster: [...roster, { player_id: playerId, position }] }
        }),
      setRoster: (entries) => set({ activeRoster: entries }),
      setWeather: (partial) =>
        set((s) => ({ weather: { ...s.weather, ...partial } })),
      reset: () => set(defaultState),
    }),
    {
      name: 'mlb-defense-scenario',
      storage: createJSONStorage(safeStorage),
      // Persist the matchup selections, not transient game state
      partialize: (s) => ({
        batterId: s.batterId,
        pitcherId: s.pitcherId,
        stadiumId: s.stadiumId,
        teamId: s.teamId,
        battingTeamId: s.battingTeamId,
      }),
    }
  )
)
