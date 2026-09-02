import { describe, it, expect } from 'vitest'
import {
  statcastToNorm,
  normToSvg,
  svgToNorm,
  normDepthToFeet,
  normXToAngle,
  gridToNorm,
  sampleGrid,
} from './fieldCoords'

describe('statcastToNorm', () => {
  it('maps home plate area to bottom center', () => {
    // hc_x=125 (center), hc_y=199 (home plate)
    const p = statcastToNorm(125, 199)
    expect(p.x).toBeCloseTo(0.5, 1)
    expect(p.y).toBeCloseTo(0.005, 2)
  })

  it('maps deep center to top middle', () => {
    const p = statcastToNorm(125, 40)
    expect(p.x).toBeCloseTo(0.5, 1)
    expect(p.y).toBeGreaterThan(0.7)
  })

  it('clamps out-of-range values to [0,1]', () => {
    const p = statcastToNorm(-50, 500)
    expect(p.x).toBe(0)
    expect(p.y).toBe(0)
    const q = statcastToNorm(500, -50)
    expect(q.x).toBe(1)
    expect(q.y).toBe(1)
  })
})

describe('normToSvg / svgToNorm', () => {
  it('are inverse operations', () => {
    const norm = { x: 0.42, y: 0.38 }
    const svg = normToSvg(norm, 700, 700)
    const back = svgToNorm(svg, 700, 700)
    expect(back.x).toBeCloseTo(norm.x, 6)
    expect(back.y).toBeCloseTo(norm.y, 6)
  })

  it('flips the y axis (SVG y grows downward)', () => {
    const top = normToSvg({ x: 0.5, y: 1 }, 700, 700)
    expect(top.y).toBe(0)
    const bottom = normToSvg({ x: 0.5, y: 0 }, 700, 700)
    expect(bottom.y).toBe(700)
  })

  it('maps x linearly', () => {
    expect(normToSvg({ x: 0, y: 0 }, 700, 700).x).toBe(0)
    expect(normToSvg({ x: 1, y: 0 }, 700, 700).x).toBe(700)
  })
})

describe('normDepthToFeet', () => {
  it('uses a 400ft-deep field', () => {
    expect(normDepthToFeet(0)).toBe(0)
    expect(normDepthToFeet(0.5)).toBe(200)
    expect(normDepthToFeet(1)).toBe(400)
  })
})

describe('normXToAngle', () => {
  it('is 0 at center, negative left, positive right', () => {
    expect(normXToAngle(0.5)).toBe(0)
    expect(normXToAngle(0)).toBe(-45)
    expect(normXToAngle(1)).toBe(45)
  })
})

describe('gridToNorm', () => {
  it('maps corners of the grid', () => {
    expect(gridToNorm(0, 0, 100)).toEqual({ x: 0, y: 0 })
    expect(gridToNorm(99, 99, 100)).toEqual({ x: 1, y: 1 })
  })
})

describe('sampleGrid', () => {
  it('samples nearest cell and clamps out-of-range', () => {
    const grid = [
      [1, 2],
      [3, 4],
    ]
    expect(sampleGrid(grid, { x: 0, y: 0 })).toBe(1)
    expect(sampleGrid(grid, { x: 1, y: 1 })).toBe(4)
    expect(sampleGrid(grid, { x: 5, y: -3 })).toBe(2) // clamped
  })

  it('returns 0 for empty rows', () => {
    expect(sampleGrid([[]], { x: 0.5, y: 0.5 })).toBe(0)
  })
})
