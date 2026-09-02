import { describe, it, expect } from 'vitest'
import { snapDir } from './WeatherControls'

// snapDir maps a meteorological "from" degree to the nearest baseball-intuitive
// wind option offered in the panel (180=out to CF, 0=in from CF, 90/270=cross).
describe('snapDir', () => {
  it('snaps near-cardinal degrees to the closest option', () => {
    expect(snapDir(190)).toBe(180) // ~S → Out to CF
    expect(snapDir(5)).toBe(0) // ~N → In from CF
    expect(snapDir(100)).toBe(90) // ~E → R → L cross
    expect(snapDir(260)).toBe(270) // ~W → L → R cross
  })

  it('returns one of the offered option degrees', () => {
    const allowed = new Set([0, 90, 135, 180, 225, 270])
    for (let d = 0; d <= 360; d += 17) {
      expect(allowed.has(snapDir(d))).toBe(true)
    }
  })
})
