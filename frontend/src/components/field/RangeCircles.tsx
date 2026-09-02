import { normToSvg } from '@/lib/fieldCoords'
import type { PlayerRangeResponse } from '@/types'

interface Props {
  ranges: PlayerRangeResponse[]
  svgWidth: number
  svgHeight: number
}

const RADII_KEYS = [
  { key: 'zone_075s' as const, label: '0.75s', opacity: 0.18 },
  { key: 'zone_125s' as const, label: '1.25s', opacity: 0.14 },
  { key: 'zone_175s' as const, label: '1.75s', opacity: 0.10 },
  { key: 'zone_225s' as const, label: '2.25s', opacity: 0.07 },
  { key: 'zone_300s' as const, label: '3.0s', opacity: 0.04 },
]

const RANGE_COLOR = '#38bdf8'

export function RangeCircles({ ranges, svgWidth, svgHeight }: Props) {
  return (
    <g>
      {ranges.map((r) => {
        const center = normToSvg(
          { x: r.center_x, y: r.center_y },
          svgWidth,
          svgHeight
        )

        return (
          <g key={r.player_id}>
            {RADII_KEYS.map(({ key, opacity }) => {
              const radiusFt = r.radii[key]
              if (!radiusFt) return null
              const radiusSvg = (radiusFt / 400) * svgHeight

              return (
                <circle
                  key={key}
                  cx={center.x}
                  cy={center.y}
                  r={radiusSvg}
                  fill={RANGE_COLOR}
                  opacity={opacity}
                  stroke={RANGE_COLOR}
                  strokeWidth={0.5}
                  strokeOpacity={opacity * 2}
                />
              )
            })}

            {r.arm_throw_range.max_distance_ft > 0 && (
              <circle
                cx={center.x}
                cy={center.y}
                r={(r.arm_throw_range.max_distance_ft / 400) * svgHeight}
                fill="none"
                stroke="#f97316"
                strokeWidth={1}
                strokeDasharray="4 3"
                opacity={0.3}
              />
            )}
          </g>
        )
      })}
    </g>
  )
}
