import { useMemo, useState } from 'react'
import * as d3 from 'd3'
import { gridToNorm, normToSvg } from '@/lib/fieldCoords'
import type { SprayChartResponse, SprayZone } from '@/types'

const W = 500
const H = 500
const HOME = { x: W / 2, y: H - 50 }
const FIELD_R = H - 100

interface Props {
  data: SprayChartResponse
}

const hitColor = d3.scaleSequential(d3.interpolateYlOrRd).domain([0, 0.6])

const ZONE_ANGLES: Record<number, { startDeg: number; endDeg: number; inner: number; outer: number }> = {
  1: { startDeg: -45, endDeg: -22.5, inner: 0.15, outer: 0.55 },
  2: { startDeg: -22.5, endDeg: 0, inner: 0.15, outer: 0.55 },
  3: { startDeg: 0, endDeg: 22.5, inner: 0.15, outer: 0.55 },
  4: { startDeg: 22.5, endDeg: 45, inner: 0.15, outer: 0.55 },
  5: { startDeg: -45, endDeg: -22.5, inner: 0.55, outer: 1.0 },
  6: { startDeg: -22.5, endDeg: 0, inner: 0.55, outer: 1.0 },
  7: { startDeg: 0, endDeg: 22.5, inner: 0.55, outer: 1.0 },
  8: { startDeg: 22.5, endDeg: 45, inner: 0.55, outer: 1.0 },
}

export function SprayChart({ data }: Props) {
  const [hoveredZone, setHoveredZone] = useState<SprayZone | null>(null)

  const heatmapRects = useMemo(() => {
    const grid = data.logistic_grid
    if (!grid.length) return null
    const size = grid.length
    const cellW = W / size
    const cellH = H / size

    // The grid is a probability mass (sums to ~1), so absolute values are
    // tiny — scale intensity relative to the hottest cell.
    let max = 0
    for (const row of grid) for (const v of row) if (v > max) max = v
    if (max <= 0) return null

    const rects: React.ReactElement[] = []
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        const rel = (grid[r]?.[c] ?? 0) / max
        if (rel < 0.08) continue
        const norm = gridToNorm(r, c, size)
        const svg = normToSvg(norm, W, H)
        rects.push(
          <rect
            key={`${r}-${c}`}
            x={svg.x - cellW / 2}
            y={svg.y - cellH / 2}
            width={cellW}
            height={cellH}
            fill={hitColor(rel * 0.6)}
            opacity={Math.min(0.7, rel * 0.8)}
          />
        )
      }
    }
    return rects
  }, [data.logistic_grid])

  return (
    <div className="flex gap-6">
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[500px]">
          <defs>
            <radialGradient id="sprayFieldGrad" cx="50%" cy="90%" r="60%">
              <stop offset="0%" stopColor="#3a7a2a" />
              <stop offset="100%" stopColor="#1e4a10" />
            </radialGradient>
            <clipPath id="sprayFairClip">
              <path d={fairPath()} />
            </clipPath>
          </defs>

          <rect width={W} height={H} fill="url(#sprayFieldGrad)" rx={6} />
          <path d={fairPath()} fill="none" stroke="#5a5a5a" strokeWidth={1} />

          {/* heatmap */}
          <g clipPath="url(#sprayFairClip)">{heatmapRects}</g>

          {/* zone arcs */}
          {data.zones.map((zone) => {
            const geo = ZONE_ANGLES[zone.zone]
            if (!geo) return null
            return (
              <path
                key={zone.zone}
                d={arcPath(geo.startDeg, geo.endDeg, geo.inner, geo.outer)}
                fill="transparent"
                stroke="#fff"
                strokeWidth={hoveredZone?.zone === zone.zone ? 2 : 0.5}
                strokeOpacity={hoveredZone?.zone === zone.zone ? 0.8 : 0.25}
                onMouseEnter={() => setHoveredZone(zone)}
                onMouseLeave={() => setHoveredZone(null)}
                style={{ cursor: 'pointer' }}
              />
            )
          })}

          {/* zone labels */}
          {data.zones.map((zone) => {
            const geo = ZONE_ANGLES[zone.zone]
            if (!geo) return null
            const midAngle = ((geo.startDeg + geo.endDeg) / 2) * (Math.PI / 180)
            const midR = ((geo.inner + geo.outer) / 2) * FIELD_R
            const lx = HOME.x + Math.sin(midAngle) * midR
            const ly = HOME.y - Math.cos(midAngle) * midR
            return (
              <text
                key={`label-${zone.zone}`}
                x={lx}
                y={ly}
                textAnchor="middle"
                dominantBaseline="central"
                className="text-[10px] font-medium"
                fill="#fff"
                fillOpacity={0.7}
                style={{ pointerEvents: 'none', textShadow: '0 1px 3px #000' }}
              >
                {(zone.hit_pct * 100).toFixed(0)}%
              </text>
            )
          })}

          {/* home plate */}
          <rect
            x={HOME.x - 4}
            y={HOME.y - 4}
            width={8}
            height={8}
            fill="#c4913a"
            transform={`rotate(45 ${HOME.x} ${HOME.y})`}
          />
        </svg>
      </div>

      {/* side panel: zone detail + summary */}
      <div className="min-w-[200px] space-y-4">
        <div>
          <h3 className="text-xs text-[color:var(--muted)] uppercase mb-1">Batter</h3>
          <p className="text-sm font-medium text-[color:var(--ink)]">{data.batter.full_name}</p>
          <p className="text-xs text-[color:var(--muted)]">
            {data.batter.position} · {data.season === 0 ? 'All seasons' : data.season}
          </p>
          <p className="text-xs text-[color:var(--muted)] mt-1">
            {data.sample_n} batted balls
            {data.recency_weighted && ' · recency-weighted'}
            {data.weather_adjusted && ' · weather adj.'}
            {data.park_adjusted && ' · park adj.'}
          </p>
        </div>

        {hoveredZone ? (
          <ZoneDetail zone={hoveredZone} />
        ) : (
          <div className="text-xs text-[color:var(--muted)]">Hover a zone for details</div>
        )}

        <div>
          <h3 className="text-xs text-[color:var(--muted)] uppercase mb-2">All Zones</h3>
          <div className="space-y-1">
            {data.zones
              .sort((a, b) => a.zone - b.zone)
              .map((z) => (
                <div
                  key={z.zone}
                  className="flex items-center gap-2 text-xs"
                  onMouseEnter={() => setHoveredZone(z)}
                  onMouseLeave={() => setHoveredZone(null)}
                >
                  <span className="w-4 text-[color:var(--muted)]">{z.zone}</span>
                  <div className="flex-1 h-3 bg-[#e6ebe1] rounded overflow-hidden">
                    <div
                      className="h-full rounded"
                      style={{
                        width: `${z.hit_pct * 100}%`,
                        backgroundColor: hitColor(z.hit_pct),
                      }}
                    />
                  </div>
                  <span className="w-10 text-right text-[color:var(--muted)]">
                    {(z.hit_pct * 100).toFixed(1)}%
                  </span>
                  <span className="w-6 text-right text-[color:var(--muted)]">n={z.n}</span>
                </div>
              ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function ZoneDetail({ zone }: { zone: SprayZone }) {
  return (
    <div className="bg-[#edf1ea] rounded p-3 space-y-2">
      <h4 className="text-xs font-medium text-[color:var(--ink)]">Zone {zone.zone}</h4>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <Stat label="Hit %" value={`${(zone.hit_pct * 100).toFixed(1)}%`} />
        <Stat label="Out %" value={`${(zone.out_pct * 100).toFixed(1)}%`} />
        <Stat label="Sample" value={String(zone.n)} />
      </div>
      <div className="text-[10px] text-[color:var(--muted)] space-y-0.5">
        <p>GB {(zone.trajectory.groundball * 100).toFixed(0)}% · FB {(zone.trajectory.flyball * 100).toFixed(0)}% · LD {(zone.trajectory.linedrive * 100).toFixed(0)}% · PU {(zone.trajectory.popup * 100).toFixed(0)}%</p>
        <p>1B {(zone.specific.single * 100).toFixed(0)}% · 2B {(zone.specific.double * 100).toFixed(0)}% · 3B {(zone.specific.triple * 100).toFixed(0)}% · HR {(zone.specific.hr * 100).toFixed(0)}%</p>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-[color:var(--muted)]">{label}</span>
      <span className="text-[color:var(--ink)]">{value}</span>
    </div>
  )
}

function fairPath(): string {
  const angle = Math.PI / 4
  const lx = HOME.x - FIELD_R * Math.sin(angle)
  const ly = HOME.y - FIELD_R * Math.cos(angle)
  const rx = HOME.x + FIELD_R * Math.sin(angle)
  const ry = ly
  return `M ${HOME.x} ${HOME.y} L ${lx} ${ly} A ${FIELD_R} ${FIELD_R} 0 0 1 ${rx} ${ry} Z`
}

function arcPath(
  startDeg: number,
  endDeg: number,
  innerPct: number,
  outerPct: number
): string {
  const toRad = (d: number) => (d * Math.PI) / 180
  const s = toRad(startDeg)
  const e = toRad(endDeg)
  const ri = innerPct * FIELD_R
  const ro = outerPct * FIELD_R

  const x1 = HOME.x + Math.sin(s) * ri
  const y1 = HOME.y - Math.cos(s) * ri
  const x2 = HOME.x + Math.sin(e) * ri
  const y2 = HOME.y - Math.cos(e) * ri
  const x3 = HOME.x + Math.sin(e) * ro
  const y3 = HOME.y - Math.cos(e) * ro
  const x4 = HOME.x + Math.sin(s) * ro
  const y4 = HOME.y - Math.cos(s) * ro

  return [
    `M ${x1} ${y1}`,
    `A ${ri} ${ri} 0 0 1 ${x2} ${y2}`,
    `L ${x3} ${y3}`,
    `A ${ro} ${ro} 0 0 0 ${x4} ${y4}`,
    'Z',
  ].join(' ')
}
