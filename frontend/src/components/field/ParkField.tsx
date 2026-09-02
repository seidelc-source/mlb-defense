import { useMemo } from 'react'
import type { StadiumLayout, WallPoint } from '@/types'

/**
 * Park-specific field rendering driven by the /stadiums/{id}/layout API.
 *
 * Everything is drawn in the app's normalized space mapped onto the SVG:
 * home plate at (0.5, 0) -> (W/2, H), 1.0 norm unit = 400 ft on both axes.
 * Wall points may fall slightly outside [0,1]; the parent SVG pads its
 * viewBox to accommodate.
 */

const FT = 400 // ft per normalized unit

interface Pt {
  x: number
  y: number
}

function n2s(x: number, y: number, W: number, H: number): Pt {
  return { x: x * W, y: (1 - y) * H }
}

/** Scale a wall point toward home plate by a feet offset (e.g. warning track). */
function towardHome(p: WallPoint, offsetFt: number): Pt {
  const scale = Math.max(0, (p.distance_ft - offsetFt) / p.distance_ft)
  return { x: 0.5 + (p.x - 0.5) * scale, y: p.y * scale }
}

export function parkFairPath(layout: StadiumLayout, W: number, H: number): string {
  const home = n2s(0.5, 0, W, H)
  const pts = layout.wall_points.map((p) => n2s(p.x, p.y, W, H))
  return [
    `M ${home.x} ${home.y}`,
    ...pts.map((p) => `L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`),
    'Z',
  ].join(' ')
}

const ANCHOR_ANGLE: Record<string, number> = {
  left_field: -45,
  left_center: -22.5,
  center_field: 0,
  right_center: 22.5,
  right_field: 45,
}

interface Props {
  layout: StadiumLayout
  svgWidth: number
  svgHeight: number
}

export function ParkField({ layout, svgWidth: W, svgHeight: H }: Props) {
  const home = n2s(0.5, 0, W, H)

  const wallPx = useMemo(
    () => layout.wall_points.map((p) => n2s(p.x, p.y, W, H)),
    [layout, W, H]
  )

  const fairPath = useMemo(() => parkFairPath(layout, W, H), [layout, W, H])

  // Warning track: band between the wall and a ~18ft inward offset
  const trackPath = useMemo(() => {
    const inner = layout.wall_points.map((p) => {
      const t = towardHome(p, 18)
      return n2s(t.x, t.y, W, H)
    })
    return [
      `M ${wallPx[0].x.toFixed(1)} ${wallPx[0].y.toFixed(1)}`,
      ...wallPx.slice(1).map((p) => `L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`),
      ...inner
        .slice()
        .reverse()
        .map((p) => `L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`),
      'Z',
    ].join(' ')
  }, [layout, wallPx, W, H])

  // Mow stripes: concentric arc bands clipped to fair territory
  const mowBands = useMemo(() => {
    const bands: string[] = []
    for (let ft = 130; ft < 440; ft += 56) {
      const r0 = (ft / FT) * H
      const r1 = ((ft + 28) / FT) * H
      const a0 = -Math.PI / 4
      const a1 = Math.PI / 4
      const p = (r: number, a: number) => ({
        x: home.x + r * Math.sin(a),
        y: home.y - r * Math.cos(a),
      })
      const s0 = p(r0, a0)
      const e0 = p(r0, a1)
      const s1 = p(r1, a1)
      const e1 = p(r1, a0)
      bands.push(
        [
          `M ${s0.x} ${s0.y}`,
          `A ${r0} ${r0} 0 0 1 ${e0.x} ${e0.y}`,
          `L ${s1.x} ${s1.y}`,
          `A ${r1} ${r1} 0 0 0 ${e1.x} ${e1.y}`,
          'Z',
        ].join(' ')
      )
    }
    return bands
  }, [home.x, home.y, H])

  // Feature wall segments: wall polyline points near the feature's anchor angle
  const featureSegments = useMemo(() => {
    return layout.feature_walls
      .filter((fw) => fw.height_ft >= 8) // only visually notable walls
      .map((fw) => {
        const anchor = ANCHOR_ANGLE[fw.key] ?? 0
        const pts = layout.wall_points
          .filter((p) => Math.abs(p.angle_deg - anchor) <= 12)
          .map((p) => n2s(p.x, p.y, W, H))
        const mid = pts[Math.floor(pts.length / 2)]
        return { ...fw, pts, mid }
      })
      .filter((seg) => seg.pts.length >= 2)
  }, [layout, W, H])

  const infield = useMemo(() => buildInfield(W, H), [W, H])

  return (
    <g>
      {/* foul ground wedge behind fair territory */}
      <path
        d={`M ${home.x} ${home.y + 40}
            L ${n2s(-0.12, 0.62, W, H).x} ${n2s(-0.12, 0.62, W, H).y}
            L ${home.x} ${home.y - 80}
            L ${n2s(1.12, 0.62, W, H).x} ${n2s(1.12, 0.62, W, H).y} Z`}
        fill="rgba(183, 127, 81, 0.30)"
      />

      {/* fair territory grass */}
      <path d={fairPath} fill="url(#parkGrass)" stroke="rgba(246,243,228,0.95)" strokeWidth={2} />

      {/* mow stripes */}
      <g clipPath="url(#fairClip)">
        {mowBands.map((d, i) =>
          i % 2 === 0 ? <path key={i} d={d} fill="rgba(255,255,255,0.05)" /> : null
        )}
      </g>

      {/* warning track */}
      <path d={trackPath} fill="rgba(165,116,76,0.85)" clipPath="url(#fairClip)" />

      {/* outfield wall line */}
      <polyline
        points={wallPx.map((p) => `${p.x},${p.y}`).join(' ')}
        fill="none"
        stroke="#4e5b4e"
        strokeWidth={4}
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* feature walls (Green Monster, Clemente Wall, ...) */}
      {featureSegments.map((seg) => (
        <g key={seg.key}>
          <polyline
            points={seg.pts.map((p) => `${p.x},${p.y}`).join(' ')}
            fill="none"
            stroke={seg.height_ft >= 30 ? '#1d5a36' : '#33413a'}
            strokeWidth={seg.height_ft >= 30 ? 9 : 7}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          {seg.mid && (
            <text
              x={seg.mid.x}
              y={seg.mid.y - 10}
              textAnchor="middle"
              fontSize={10}
              fontWeight={900}
              fill="#fff"
              style={{ paintOrder: 'stroke', stroke: 'rgba(24,33,27,0.7)', strokeWidth: 3 }}
            >
              {Math.round(seg.height_ft)} ft
            </text>
          )}
        </g>
      ))}

      {/* foul lines */}
      <line
        x1={home.x} y1={home.y}
        x2={wallPx[0].x} y2={wallPx[0].y}
        stroke="rgba(255,255,255,0.9)" strokeWidth={2.5}
      />
      <line
        x1={home.x} y1={home.y}
        x2={wallPx[wallPx.length - 1].x} y2={wallPx[wallPx.length - 1].y}
        stroke="rgba(255,255,255,0.9)" strokeWidth={2.5}
      />

      {/* infield */}
      {infield}

      {/* distance marker pills — just inside the wall, like MLB.com */}
      {layout.distance_markers.map((m) => {
        const inside = towardHome(
          { ...m, angle_deg: 0 } as unknown as WallPoint,
          26
        )
        const p = n2s(inside.x, inside.y, W, H)
        return (
          <g key={m.key} pointerEvents="none">
            <rect
              x={p.x - 17} y={p.y - 9}
              width={34} height={18}
              rx={9}
              fill="rgba(54,61,57,0.88)"
              stroke="rgba(255,250,232,0.85)"
              strokeWidth={1}
            />
            <text
              x={p.x} y={p.y + 3.5}
              textAnchor="middle"
              fontSize={10}
              fontWeight={900}
              fill="#fff7df"
            >
              {m.label}
            </text>
          </g>
        )
      })}

      {/* park name plate */}
      <g pointerEvents="none">
        <rect
          x={-56} y={-64}
          width={236} height={46}
          rx={8}
          fill="rgba(48,55,52,0.82)"
          stroke="rgba(255,255,255,0.35)"
        />
        <text x={-44} y={-45} fontSize={14} fontWeight={800} fill="#fff">
          {layout.name}
        </text>
        <text x={-44} y={-28} fontSize={10} fontWeight={700} fill="#d9ebd4" style={{ textTransform: 'uppercase' }}>
          {layout.city} · {layout.roof_type} roof · {layout.surface}
        </text>
      </g>
    </g>
  )
}

/** Infield geometry in true scale: 90ft bases, 60.5ft mound. */
function buildInfield(W: number, H: number) {
  const home = n2s(0.5, 0, W, H)
  const baseFt = 90
  const diag = (baseFt / FT) * Math.SQRT1_2 // norm offset along 45°
  const first = n2s(0.5 + diag, diag, W, H)
  const second = n2s(0.5, (baseFt * Math.SQRT2) / FT, W, H)
  const third = n2s(0.5 - diag, diag, W, H)
  const mound = n2s(0.5, 60.5 / FT, W, H)
  const moundR = (9 / FT) * H // 18 ft diameter
  const dirtR = (95 / FT) * H
  // centered so the arc's bottom edge meets home plate
  const dirtC = n2s(0.5, 95 / FT, W, H)

  const bases = [home, first, second, third]

  return (
    <g>
      <circle cx={dirtC.x} cy={dirtC.y} r={dirtR} fill="#b77f51" opacity={0.95} />
      <polygon
        points={bases.map((b) => `${b.x},${b.y}`).join(' ')}
        fill="rgba(77,134,75,0.97)"
        stroke="#d8a16c"
        strokeWidth={5}
        strokeLinejoin="round"
      />
      <circle cx={mound.x} cy={mound.y} r={moundR} fill="#a96f43" />
      <rect x={mound.x - 4} y={mound.y - 1.5} width={8} height={3} fill="#fbfbf2" rx={1} />
      {bases.map((b, i) => (
        <rect
          key={i}
          x={b.x - 5} y={b.y - 5}
          width={10} height={10}
          fill="#fbfbf2"
          stroke="rgba(81,70,56,0.6)"
          strokeWidth={1}
          transform={`rotate(45 ${b.x} ${b.y})`}
        />
      ))}
    </g>
  )
}
