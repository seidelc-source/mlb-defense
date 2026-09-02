import { describe, it, expect, beforeEach } from 'vitest'
import { useScenarioStore } from './scenarioStore'
import { useAlignmentStore } from './alignmentStore'
import type { AlignmentResponse } from '@/types'

function makeAlignment(id: string): AlignmentResponse {
  return {
    alignment_id: id,
    shift_type: 'standard',
    fielder_positions: {},
    coverage_map: [],
    overlap_zones: [],
    predicted_oaa_delta: 0.05,
    predicted_hit_pct: 0.3,
    predicted_out_pct: 0.7,
    confidence: 0.6,
    optimize_for: 'balanced',
    factors_applied: [],
    alternatives: [],
    created_at: new Date().toISOString(),
  }
}

describe('scenarioStore', () => {
  beforeEach(() => {
    useScenarioStore.getState().reset()
  })

  it('sets matchup ids', () => {
    useScenarioStore.getState().setBatter('b1')
    useScenarioStore.getState().setPitcher('p1')
    expect(useScenarioStore.getState().batterId).toBe('b1')
    expect(useScenarioStore.getState().pitcherId).toBe('p1')
  })

  it('toggles runners independently', () => {
    useScenarioStore.getState().setRunners({ on_2b: true })
    const runners = useScenarioStore.getState().runners
    expect(runners.on_2b).toBe(true)
    expect(runners.on_1b).toBe(false)
    expect(runners.on_3b).toBe(false)
  })

  it('setRosterEntry replaces existing position entry', () => {
    const s = useScenarioStore.getState()
    s.setRosterEntry('SS', 'player-a')
    s.setRosterEntry('SS', 'player-b')
    const roster = useScenarioStore.getState().activeRoster
    expect(roster).toHaveLength(1)
    expect(roster[0]).toEqual({ player_id: 'player-b', position: 'SS' })
  })

  it('setRoster replaces the whole roster', () => {
    const s = useScenarioStore.getState()
    s.setRosterEntry('SS', 'x')
    s.setRoster([
      { player_id: 'a', position: '1B' },
      { player_id: 'b', position: '2B' },
    ])
    expect(useScenarioStore.getState().activeRoster).toHaveLength(2)
  })

  it('reset restores defaults', () => {
    const s = useScenarioStore.getState()
    s.setBatter('b1')
    s.setOuts(2)
    s.reset()
    expect(useScenarioStore.getState().batterId).toBeNull()
    expect(useScenarioStore.getState().outs).toBe(0)
  })
})

describe('alignmentStore', () => {
  beforeEach(() => {
    useAlignmentStore.setState({ current: null, history: [], isLoading: false, error: null })
  })

  it('setCurrent pushes previous into history', () => {
    const store = useAlignmentStore.getState()
    store.setCurrent(makeAlignment('a1'))
    useAlignmentStore.getState().setCurrent(makeAlignment('a2'))
    const state = useAlignmentStore.getState()
    expect(state.current?.alignment_id).toBe('a2')
    expect(state.history.some((h) => h.alignment_id === 'a1')).toBe(true)
  })

  it('caps history at 20 entries', () => {
    for (let i = 0; i < 30; i++) {
      useAlignmentStore.getState().setCurrent(makeAlignment(`a${i}`))
    }
    expect(useAlignmentStore.getState().history.length).toBeLessThanOrEqual(20)
  })

  it('tracks loading and error state', () => {
    useAlignmentStore.getState().setLoading(true)
    expect(useAlignmentStore.getState().isLoading).toBe(true)
    useAlignmentStore.getState().setError('boom')
    expect(useAlignmentStore.getState().error).toBe('boom')
  })
})
