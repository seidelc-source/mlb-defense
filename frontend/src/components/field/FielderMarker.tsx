import { useState, useCallback, useRef } from 'react'
import { svgToNorm, type Point } from '@/lib/fieldCoords'

interface Props {
  position: string
  playerName: string
  cx: number
  cy: number
  catchProb: number
  svgWidth: number
  svgHeight: number
  illegal?: boolean
  moved?: boolean
  onDrag?: (norm: Point) => void
}

export function FielderMarker({
  position,
  playerName,
  cx,
  cy,
  catchProb,
  svgWidth,
  svgHeight,
  illegal = false,
  moved = false,
  onDrag,
}: Props) {
  const [dragging, setDragging] = useState(false)
  const [pos, setPos] = useState({ x: cx, y: cy })
  const svgRef = useRef<SVGElement | null>(null)

  const toSvgCoords = useCallback(
    (e: React.MouseEvent | MouseEvent): Point | null => {
      const svg = svgRef.current?.closest('svg')
      if (!svg) return null
      const ctm = svg.getScreenCTM()
      if (!ctm) return null
      return {
        x: (e.clientX - ctm.e) / ctm.a,
        y: (e.clientY - ctm.f) / ctm.d,
      }
    },
    []
  )

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (!onDrag) return
      e.stopPropagation()
      ;(e.target as Element).setPointerCapture(e.pointerId)
      setPos({ x: cx, y: cy })
      setDragging(true)
    },
    [onDrag, cx, cy]
  )

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!dragging) return
      const pt = toSvgCoords(e)
      if (pt) setPos(pt)
    },
    [dragging, toSvgCoords]
  )

  const handlePointerUp = useCallback(
    (e: React.PointerEvent) => {
      if (!dragging) return
      setDragging(false)
      ;(e.target as Element).releasePointerCapture(e.pointerId)
      const pt = toSvgCoords(e)
      if (pt && onDrag) {
        onDrag(svgToNorm(pt, svgWidth, svgHeight))
      }
    },
    [dragging, toSvgCoords, onDrag, svgWidth, svgHeight]
  )

  const displayX = dragging ? pos.x : cx
  const displayY = dragging ? pos.y : cy

  const ringColor = illegal ? 'var(--danger)' : 'var(--gold)'
  const dotStroke = illegal ? 'var(--danger)' : moved ? 'var(--gold)' : 'var(--clay-dark)'

  return (
    <g
      ref={(el) => { svgRef.current = el }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      style={{ cursor: onDrag ? (dragging ? 'grabbing' : 'grab') : 'default' }}
    >
      {/* coverage / status ring */}
      {(catchProb > 0 || illegal || dragging) && (
        <circle
          cx={displayX}
          cy={displayY}
          r={16}
          fill={illegal ? 'rgba(155,47,47,0.12)' : 'rgba(214,165,72,0.15)'}
          stroke={ringColor}
          strokeWidth={1.5}
          opacity={dragging ? 0.95 : illegal ? 0.9 : Math.max(0.35, catchProb * 0.7)}
        />
      )}

      {/* main dot — cream with clay border */}
      <circle
        cx={displayX}
        cy={displayY}
        r={dragging ? 12 : 10}
        fill="#f5f0e2"
        stroke={dotStroke}
        strokeWidth={2}
      />
      <text
        x={displayX}
        y={displayY + 3}
        textAnchor="middle"
        fontSize={8}
        fontWeight={900}
        fill="var(--ink)"
        style={{ pointerEvents: 'none' }}
      >
        {position}
      </text>

      {/* player name under the dot */}
      <text
        x={displayX}
        y={displayY + 22}
        textAnchor="middle"
        fontSize={9}
        fontWeight={700}
        fill="#fff"
        style={{ pointerEvents: 'none', paintOrder: 'stroke', stroke: 'rgba(24,33,27,0.65)', strokeWidth: 2.5 }}
      >
        {playerName !== position ? playerName : ''}
      </text>

      <title>{`${position}: ${playerName}${illegal ? ' — ILLEGAL position' : ''}`}</title>
    </g>
  )
}
