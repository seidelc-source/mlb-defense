import { useRef, useEffect, useMemo } from 'react'
import * as d3 from 'd3'
import { normToSvg, gridToNorm, type Point } from '@/lib/fieldCoords'
import { FielderMarker } from './FielderMarker'
import { RangeCircles } from './RangeCircles'
import { ParkField, parkFairPath } from './ParkField'
import type { AlignmentResponse, GameWeather, PlayerRangeResponse, StadiumLayout } from '@/types'

const SVG_W = 700
const SVG_H = 700
const HOME = { x: SVG_W / 2, y: SVG_H - 60 }
const FIELD_R = SVG_H - 120

interface Props {
  alignment: AlignmentResponse | null
  layout?: StadiumLayout | null
  customPositions?: Record<string, Point> | null
  illegalPositions?: string[]
  weather?: GameWeather | null
  ranges?: PlayerRangeResponse[]
  showRanges?: boolean
  onFielderDrag?: (positionCode: string, norm: Point) => void
}

const heatColor = d3
  .scaleSequential(d3.interpolateYlOrRd)
  .domain([0, 0.5])

function buildHeatmapPath(grid: number[][]): string {
  if (!grid.length) return ''
  const size = grid.length
  const cellW = SVG_W / size
  const cellH = SVG_H / size
  const rects: string[] = []

  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      const val = grid[r]?.[c] ?? 0
      if (val < 0.02) continue
      const norm = gridToNorm(r, c, size)
      const svg = normToSvg(norm, SVG_W, SVG_H)
      rects.push(
        `<rect x="${svg.x - cellW / 2}" y="${svg.y - cellH / 2}" ` +
          `width="${cellW}" height="${cellH}" ` +
          `fill="${heatColor(val)}" opacity="${Math.min(0.55, val * 1.6)}"/>`
      )
    }
  }
  return rects.join('')
}

export function FieldCanvas({
  alignment,
  layout = null,
  customPositions,
  illegalPositions = [],
  weather,
  ranges,
  showRanges = true,
  onFielderDrag,
}: Props) {
  const heatRef = useRef<SVGGElement>(null)

  const coverageGrid = alignment?.coverage_map ?? []

  useEffect(() => {
    if (!heatRef.current) return
    heatRef.current.innerHTML = buildHeatmapPath(coverageGrid)
  }, [coverageGrid])

  // Recommended positions from the alignment (the "targets")
  const recommended = useMemo(() => {
    if (!alignment) return null
    const map: Record<string, Point> = {}
    for (const [pos, fp] of Object.entries(alignment.fielder_positions)) {
      map[pos] = { x: fp.x, y: fp.y }
    }
    return map
  }, [alignment])

  // What we actually draw: custom (dragged) positions override recommended.
  // The alignment only covers the 7 fielders — battery (C/P) stays static.
  const positions = useMemo(() => {
    if (!alignment) return defaultPositions()
    const fielders = Object.entries(alignment.fielder_positions).map(([pos, fp]) => {
      const norm = customPositions?.[pos] ?? { x: fp.x, y: fp.y }
      return {
        pos,
        playerId: fp.player_id,
        playerName: fp.player_name,
        norm,
        moved:
          !!customPositions?.[pos] &&
          (Math.abs(norm.x - fp.x) > 0.005 || Math.abs(norm.y - fp.y) > 0.005),
        catchProb: fp.catch_prob_zone,
        svg: normToSvg(norm, SVG_W, SVG_H),
      }
    })
    for (const [pos, norm] of [['P', { x: 0.5, y: 0.151 }], ['C', { x: 0.5, y: 0.02 }]] as const) {
      if (!alignment.fielder_positions[pos]) {
        fielders.push({
          pos,
          playerId: pos,
          playerName: pos,
          norm,
          moved: false,
          catchProb: 0,
          svg: normToSvg(norm, SVG_W, SVG_H),
        })
      }
    }
    return fielders
  }, [alignment, customPositions])

  const fairPath = layout ? parkFairPath(layout, SVG_W, SVG_H) : fairTerritoryPath()
  const viewBox = layout
    ? `-95 -80 890 880`
    : `0 0 ${SVG_W} ${SVG_H}`

  return (
    <svg viewBox={viewBox} className="w-full h-full" style={{ maxHeight: '100%' }}>
      <defs>
        <radialGradient id="fieldGrad" cx="50%" cy="85%" r="75%">
          <stop offset="0%" stopColor="#5e8f58" />
          <stop offset="70%" stopColor="#426f48" />
          <stop offset="100%" stopColor="#28533a" />
        </radialGradient>
        <radialGradient id="parkGrass" cx="50%" cy="100%" r="110%">
          <stop offset="0%" stopColor="#5e8f58" />
          <stop offset="65%" stopColor="#477149" />
          <stop offset="100%" stopColor="#2e5a3d" />
        </radialGradient>
        <clipPath id="fairClip">
          <path d={fairPath} />
        </clipPath>
      </defs>

      {/* surround */}
      <rect
        x={layout ? -95 : 0}
        y={layout ? -80 : 0}
        width={layout ? 890 : SVG_W}
        height={layout ? 880 : SVG_H}
        fill="#b8bfbd"
        rx={10}
      />

      {layout ? (
        <ParkField layout={layout} svgWidth={SVG_W} svgHeight={SVG_H} />
      ) : (
        <>
          {/* foul ground tint */}
          <path d={foulGroundPath()} fill="rgba(188, 129, 83, 0.18)" />

          {/* fair territory grass */}
          <path d={fairTerritoryPath()} fill="url(#fieldGrad)" stroke="rgba(246,243,228,0.9)" strokeWidth={2} />

          {/* warning track */}
          <path d={warningTrackPath()} fill="none" stroke="rgba(165,116,76,0.9)" strokeWidth={10} />

          {/* foul lines */}
          <FoulLines />

          {/* infield dirt + bases */}
          <InfieldDiamond />
        </>
      )}

      {/* heatmap overlay clipped to fair territory */}
      <g clipPath="url(#fairClip)" ref={heatRef} />

      {/* range circles */}
      {showRanges && ranges && ranges.length > 0 && (
        <g clipPath="url(#fairClip)">
          <RangeCircles ranges={ranges} svgWidth={SVG_W} svgHeight={SVG_H} />
        </g>
      )}

      {/* wind arrow */}
      {weather && weather.wind_speed_mph != null && weather.wind_speed_mph > 1 && (
        <WindArrow weather={weather} />
      )}

      {/* dashed lines + target markers from dragged fielders back to recommendation */}
      {recommended &&
        positions
          .filter((p) => p.moved && recommended[p.pos])
          .map((p) => {
            const target = normToSvg(recommended[p.pos], SVG_W, SVG_H)
            return (
              <g key={`target-${p.pos}`} pointerEvents="none">
                <line
                  x1={p.svg.x}
                  y1={p.svg.y}
                  x2={target.x}
                  y2={target.y}
                  stroke="rgba(216,238,244,0.9)"
                  strokeWidth={1.5}
                  strokeDasharray="6 4"
                />
                <circle
                  cx={target.x}
                  cy={target.y}
                  r={9}
                  fill="rgba(27,72,83,0.78)"
                  stroke="#d8eef4"
                  strokeWidth={1.5}
                />
                <text
                  x={target.x}
                  y={target.y + 3}
                  textAnchor="middle"
                  fontSize={7}
                  fontWeight={900}
                  fill="#fff"
                >
                  {p.pos}
                </text>
              </g>
            )
          })}

      {/* fielder markers */}
      {positions.map((p) => (
        <FielderMarker
          key={p.pos}
          position={p.pos}
          playerName={p.playerName}
          cx={p.svg.x}
          cy={p.svg.y}
          catchProb={p.catchProb}
          svgWidth={SVG_W}
          svgHeight={SVG_H}
          illegal={illegalPositions.includes(p.pos)}
          moved={p.moved}
          onDrag={
            onFielderDrag && !['C', 'P'].includes(p.pos)
              ? (norm) => onFielderDrag(p.pos, norm)
              : undefined
          }
        />
      ))}
    </svg>
  )
}

function fairTerritoryPath(): string {
  const angle = Math.PI / 4
  const lx = HOME.x - FIELD_R * Math.sin(angle)
  const ly = HOME.y - FIELD_R * Math.cos(angle)
  const rx = HOME.x + FIELD_R * Math.sin(angle)
  const ry = ly
  return [
    `M ${HOME.x} ${HOME.y}`,
    `L ${lx} ${ly}`,
    `A ${FIELD_R} ${FIELD_R} 0 0 1 ${rx} ${ry}`,
    'Z',
  ].join(' ')
}

function foulGroundPath(): string {
  // Wedges outside the foul lines near home plate
  const angle = Math.PI / 4
  const r = FIELD_R * 0.45
  const lx = HOME.x - r * Math.sin(angle)
  const ly = HOME.y - r * Math.cos(angle)
  const rx = HOME.x + r * Math.sin(angle)
  return [
    `M ${HOME.x} ${HOME.y}`,
    `L ${lx - 40} ${ly + 40}`,
    `L ${HOME.x} ${SVG_H}`,
    `L ${rx + 40} ${ly + 40}`,
    'Z',
  ].join(' ')
}

function warningTrackPath(): string {
  const angle = Math.PI / 4
  const r = FIELD_R - 5
  const lx = HOME.x - r * Math.sin(angle)
  const ly = HOME.y - r * Math.cos(angle)
  const rx = HOME.x + r * Math.sin(angle)
  return `M ${lx} ${ly} A ${r} ${r} 0 0 1 ${rx} ${ly}`
}

function FoulLines() {
  const angle = Math.PI / 4
  const lx = HOME.x - FIELD_R * Math.sin(angle)
  const ly = HOME.y - FIELD_R * Math.cos(angle)
  const rx = HOME.x + FIELD_R * Math.sin(angle)
  return (
    <g>
      <line x1={HOME.x} y1={HOME.y} x2={lx} y2={ly} stroke="rgba(255,255,255,0.85)" strokeWidth={2} />
      <line x1={HOME.x} y1={HOME.y} x2={rx} y2={ly} stroke="rgba(255,255,255,0.85)" strokeWidth={2} />
    </g>
  )
}

function InfieldDiamond() {
  const dirtR = FIELD_R * 0.24
  const baseDist = FIELD_R * 0.155
  const bases = [
    { x: HOME.x, y: HOME.y },
    { x: HOME.x + baseDist, y: HOME.y - baseDist },
    { x: HOME.x, y: HOME.y - baseDist * 2 },
    { x: HOME.x - baseDist, y: HOME.y - baseDist },
  ]
  const moundY = HOME.y - baseDist * 0.95

  return (
    <g>
      {/* dirt arc */}
      <circle cx={HOME.x} cy={HOME.y - dirtR * 0.85} r={dirtR} fill="#b77f51" opacity={0.92} />
      {/* infield grass square */}
      <polygon
        points={bases.map((b) => `${b.x},${b.y}`).join(' ')}
        fill="rgba(77,134,75,0.96)"
        stroke="#d8a16c"
        strokeWidth={5}
        strokeLinejoin="round"
      />
      {/* mound */}
      <circle cx={HOME.x} cy={moundY} r={9} fill="#b77f51" />
      <rect x={HOME.x - 4} y={moundY - 1} width={8} height={2} fill="#fbfbf2" rx={0.5} />
      {/* bases */}
      {bases.map((b, i) => (
        <rect
          key={i}
          x={b.x - 5}
          y={b.y - 5}
          width={10}
          height={10}
          fill="#fbfbf2"
          stroke="rgba(81,70,56,0.6)"
          strokeWidth={1}
          transform={`rotate(45 ${b.x} ${b.y})`}
        />
      ))}
    </g>
  )
}

function WindArrow({ weather }: { weather: GameWeather }) {
  const wx = weather.wind_x_component ?? 0
  const wy = weather.wind_y_component ?? 0
  const mag = Math.sqrt(wx * wx + wy * wy)
  if (mag < 0.5) return null
  const angleRad = Math.atan2(-wy, wx) // SVG y down
  const cx = SVG_W - 70
  const cy = 70
  const len = Math.min(30, 10 + mag * 2)
  const x2 = cx + Math.cos(angleRad) * len
  const y2 = cy + Math.sin(angleRad) * len

  return (
    <g pointerEvents="none">
      <circle cx={cx} cy={cy} r={36} fill="rgba(48,55,52,0.72)" stroke="rgba(255,255,255,0.4)" />
      <line
        x1={cx - Math.cos(angleRad) * len}
        y1={cy - Math.sin(angleRad) * len}
        x2={x2}
        y2={y2}
        stroke="#d6e8ef"
        strokeWidth={2.5}
        markerEnd="url(#windHead)"
      />
      <defs>
        <marker id="windHead" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#d6e8ef" />
        </marker>
      </defs>
      <text x={cx} y={cy + 26} textAnchor="middle" fontSize={9} fontWeight={800} fill="#fff">
        {Math.round(weather.wind_speed_mph ?? 0)} mph
      </text>
    </g>
  )
}

function defaultPositions() {
  const defaults: Record<string, { x: number; y: number }> = {
    P:  { x: 0.50, y: 0.18 },
    C:  { x: 0.50, y: 0.05 },
    '1B': { x: 0.62, y: 0.28 },
    '2B': { x: 0.58, y: 0.38 },
    SS:  { x: 0.42, y: 0.38 },
    '3B': { x: 0.38, y: 0.28 },
    LF:  { x: 0.18, y: 0.72 },
    CF:  { x: 0.50, y: 0.82 },
    RF:  { x: 0.82, y: 0.72 },
  }
  return Object.entries(defaults).map(([pos, norm]) => ({
    pos,
    playerId: pos,
    playerName: pos,
    norm,
    moved: false,
    catchProb: 0,
    svg: normToSvg(norm, SVG_W, SVG_H),
  }))
}
