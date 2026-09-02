/**
 * fieldCoords.ts
 *
 * Single source of truth for all coordinate conversions in the app.
 *
 * Three coordinate systems:
 *
 *   Statcast  — origin at home plate, hc_x horizontal (right = higher),
 *               hc_y inverted (up the field = lower value).
 *               Typical range: hc_x 0–250, hc_y 0–200.
 *
 *   Normalized — 0–1 grid matching backend coverage_map / logistic_grid.
 *               (0,0) = left field foul line / warning track corner.
 *               (1,0) = right field foul line / warning track corner.
 *               (0.5,1) = center field wall.
 *               (0.5,0) = home plate area.
 *
 *   SVG px    — origin top-left of the SVG viewBox.
 *               Width and height passed in from FieldCanvas.
 */

export interface Point {
  x: number
  y: number
}

// Statcast → normalized
export function statcastToNorm(hcX: number, hcY: number): Point {
  // Rough empirical calibration for MLB fields
  const nx = Math.max(0, Math.min(1, (hcX - 25) / 200))
  const ny = Math.max(0, Math.min(1, 1 - hcY / 200))
  return { x: nx, y: ny }
}

// Normalized → SVG pixels
export function normToSvg(norm: Point, svgWidth: number, svgHeight: number): Point {
  return {
    x: norm.x * svgWidth,
    y: (1 - norm.y) * svgHeight, // SVG y increases downward
  }
}

// SVG pixels → normalized
export function svgToNorm(svg: Point, svgWidth: number, svgHeight: number): Point {
  return {
    x: svg.x / svgWidth,
    y: 1 - svg.y / svgHeight,
  }
}

// Statcast → SVG pixels (convenience)
export function statcastToSvg(
  hcX: number,
  hcY: number,
  svgWidth: number,
  svgHeight: number
): Point {
  return normToSvg(statcastToNorm(hcX, hcY), svgWidth, svgHeight)
}

// Normalized depth (0–1) → feet from home plate (~400ft deep center field)
export function normDepthToFeet(normY: number): number {
  return Math.round(normY * 400)
}

// Normalized x (0–1) → angle from center-field axis in degrees
// 0° = straight center, positive = toward right field
export function normXToAngle(normX: number): number {
  return Math.round((normX - 0.5) * 90)
}

// Grid index → normalized coordinates (for coverage_map lookups)
export function gridToNorm(
  row: number,
  col: number,
  gridSize = 100
): Point {
  return {
    x: col / (gridSize - 1),
    y: row / (gridSize - 1),
  }
}

// Sample the coverage_map grid at a normalized coordinate
export function sampleGrid(
  grid: number[][],
  norm: Point
): number {
  const size = grid.length
  const row = Math.max(0, Math.min(size - 1, Math.round(norm.y * (size - 1))))
  const col = Math.max(0, Math.min(size - 1, Math.round(norm.x * (size - 1))))
  return grid[row]?.[col] ?? 0
}
