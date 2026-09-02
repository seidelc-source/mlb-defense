import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { PitcherCard } from './PlayerProfile'
import type { PitcherProfile } from '@/types'

function makeProfile(overrides: Partial<PitcherProfile> = {}): PitcherProfile {
  return {
    player: {
      id: 'p1', full_name: 'Test Pitcher', position: 'P',
      throws: 'R', bats: 'R', team_id: null, active: true,
    },
    season: 2024,
    role: 'SP',
    pitcher_type: 'groundball',
    groundball_pct: 0.55,
    flyball_pct: 0.2,
    linedrive_pct: 0.18,
    popup_pct: 0.05,
    strikeout_pct: 0.28,
    walk_pct: 0.07,
    avg_velocity_mph: 92.5,
    avg_fastball_mph: 95.1,
    max_fastball_mph: 98.3,
    spin_rate_avg: 2300,
    pitch_mix: { FF: 0.5, SL: 0.3, CH: 0.2 },
    ...overrides,
  }
}

describe('PitcherCard', () => {
  it('renders role, type, season and key tendencies', () => {
    const { container } = render(<PitcherCard profile={makeProfile()} />)
    const text = container.textContent ?? ''
    expect(text).toContain('Pitching Profile — 2024')
    expect(text).toContain('SP')
    expect(text).toContain('groundball')
    expect(text).toContain('55.0%') // groundball_pct
    expect(text).toContain('92.5 mph') // avg velocity
    expect(text).toContain('2300 rpm') // spin
  })

  it('renders pitch-mix entries with rounded percentages', () => {
    const { container } = render(<PitcherCard profile={makeProfile()} />)
    const text = container.textContent ?? ''
    expect(text).toContain('FF')
    expect(text).toContain('SL')
    expect(text).toContain('CH')
    expect(text).toContain('50%') // FF share
  })

  it('shows an em dash for missing values', () => {
    const { container } = render(
      <PitcherCard
        profile={makeProfile({ avg_velocity_mph: null, spin_rate_avg: null, pitch_mix: null })}
      />,
    )
    expect(container.textContent ?? '').toContain('—')
  })
})
