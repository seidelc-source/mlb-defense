import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { FieldCanvas } from './FieldCanvas'
import type { AlignmentResponse } from '@/types'

function makeAlignment(): AlignmentResponse {
  return {
    alignment_id: 'test-1',
    shift_type: 'optimized',
    fielder_positions: {
      SS: {
        player_id: 'p-ss',
        player_name: 'Test Shortstop',
        x: 0.42,
        y: 0.38,
        depth_ft: 152,
        angle_deg: -7.2,
        catch_prob_zone: 0.4,
      },
      CF: {
        player_id: 'p-cf',
        player_name: 'Test Centerfielder',
        x: 0.5,
        y: 0.82,
        depth_ft: 328,
        angle_deg: 0,
        catch_prob_zone: 0.6,
      },
    },
    coverage_map: [],
    overlap_zones: [],
    predicted_oaa_delta: 0.1,
    predicted_hit_pct: 0.2,
    predicted_out_pct: 0.8,
    confidence: 0.6,
    optimize_for: 'balanced',
    factors_applied: [],
    alternatives: [],
    created_at: new Date().toISOString(),
  }
}

describe('FieldCanvas', () => {
  it('renders all nine default fielders when no alignment is given', () => {
    const { container } = render(<FieldCanvas alignment={null} />)
    const labels = Array.from(container.querySelectorAll('text')).map((t) => t.textContent)
    for (const pos of ['P', 'C', '1B', '2B', 'SS', '3B', 'LF', 'CF', 'RF']) {
      expect(labels).toContain(pos)
    }
  })

  it('renders fielders from the alignment with player names', () => {
    const { container } = render(<FieldCanvas alignment={makeAlignment()} />)
    const text = container.textContent ?? ''
    expect(text).toContain('Test Shortstop')
    expect(text).toContain('Test Centerfielder')
  })

  it('shows a dashed target line when a fielder is dragged away', () => {
    const alignment = makeAlignment()
    const { container } = render(
      <FieldCanvas
        alignment={alignment}
        customPositions={{ SS: { x: 0.3, y: 0.42 } }}
      />
    )
    const dashed = Array.from(container.querySelectorAll('line')).filter((l) =>
      l.getAttribute('stroke-dasharray')
    )
    expect(dashed.length).toBeGreaterThanOrEqual(1)
  })

  it('does not show target lines when positions match the recommendation', () => {
    const alignment = makeAlignment()
    const { container } = render(
      <FieldCanvas alignment={alignment} customPositions={{ SS: { x: 0.42, y: 0.38 } }} />
    )
    const dashed = Array.from(container.querySelectorAll('line')).filter((l) =>
      l.getAttribute('stroke-dasharray')
    )
    expect(dashed).toHaveLength(0)
  })

  it('renders a wind arrow when weather has wind', () => {
    const { container } = render(
      <FieldCanvas
        alignment={makeAlignment()}
        weather={{
          id: 'w1',
          game_id: 'g1',
          stadium_id: null,
          game_date: '2024-06-01',
          temperature_f: 72,
          humidity_pct: 40,
          wind_speed_mph: 12,
          wind_direction_label: 'out',
          wind_speed_level: 3,
          conditions: 'clear',
          wind_x_component: 8,
          wind_y_component: 6,
        }}
      />
    )
    expect(container.textContent).toContain('12 mph')
  })
})
