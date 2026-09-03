import type { AlignmentResponse } from '@/types'

interface Props {
  alignment: AlignmentResponse | null
  isLoading: boolean
  error: string | null
}

export function AlignmentResults({ alignment, isLoading, error }: Props) {
  if (isLoading) {
    return (
      <div className="p-4 text-sm animate-pulse" style={{ color: 'var(--muted)' }}>
        Computing alignment...
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 text-sm" style={{ color: 'var(--danger)' }}>
        {error}
      </div>
    )
  }

  if (!alignment) {
    return (
      <div className="p-4 text-sm" style={{ color: 'var(--muted)' }}>
        Configure a scenario and click "Get Alignment" to see recommendations.
      </div>
    )
  }

  return (
    <div className="p-4 space-y-4 overflow-y-auto">
      <h2 className="panel-kicker">Recommendation</h2>

      {/* score strip — big numbers */}
      <div className="grid grid-cols-3 gap-2">
        <div
          className="score-cell"
          title="Predicted outs added vs the standard alignment — outcome-validated for direction"
        >
          <strong style={{ color: alignment.predicted_oaa_delta >= 0 ? 'var(--ok)' : 'var(--danger)' }}>
            {formatSigned(alignment.predicted_oaa_delta, 2)}
          </strong>
          <span>OAA Δ</span>
        </div>
        <div
          className="score-cell"
          title="League-calibrated scale — not specific to this batter"
        >
          <strong>{(alignment.predicted_out_pct * 100).toFixed(0)}%</strong>
          <span>out (lg)</span>
        </div>
        <div className="score-cell" title="Sample-size heuristic, not a calibrated uncertainty">
          <strong>{(alignment.confidence * 100).toFixed(0)}%</strong>
          <span>conf</span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <span
          className="text-xs font-extrabold px-2.5 py-1 rounded-full"
          title="Positioning template label — shift selection is a heuristic, not outcome-validated"
          style={{ background: '#f2dfc9', color: 'var(--clay-dark)', border: '1px solid var(--clay)' }}
        >
          {alignment.shift_type.replace(/_/g, ' ')}
        </span>
        <span className="text-xs" style={{ color: 'var(--muted)' }}>
          hit {(alignment.predicted_hit_pct * 100).toFixed(1)}% (lg)
        </span>
      </div>

      <p className="text-[11px] leading-snug" style={{ color: 'var(--muted)' }}>
        OAA Δ is the outcome-validated number. The shift label is a heuristic template — picking
        when to shift this way hasn't been shown to beat shifting broadly. Out/hit % are
        league-calibrated averages, not batter-specific.
      </p>

      {alignment.pitcher_type && (
        <div className="text-xs" style={{ color: 'var(--muted)' }}>
          Pitcher:{' '}
          <span className="font-bold capitalize" style={{ color: 'var(--ink)' }}>
            {alignment.pitcher_type}
          </span>
          {alignment.pitcher_groundball_pct != null && (
            <> · {(alignment.pitcher_groundball_pct * 100).toFixed(0)}% GB</>
          )}
        </div>
      )}

      {alignment.weather_carry != null && Math.abs(alignment.weather_carry - 1) > 0.005 && (
        <div className="text-xs" style={{ color: 'var(--muted)' }}>
          Carry:{' '}
          <span
            className="font-bold"
            style={{ color: alignment.weather_carry >= 1 ? 'var(--ok)' : 'var(--danger)' }}
          >
            {alignment.weather_carry >= 1 ? '+' : ''}
            {((alignment.weather_carry - 1) * 100).toFixed(0)}%
          </span>{' '}
          {alignment.weather_carry >= 1 ? '(plays deeper)' : '(plays shallower)'}
        </div>
      )}

      {alignment.factors_applied.length > 0 && (
        <div>
          <h3 className="panel-kicker mb-1">Factors Applied</h3>
          <div className="flex flex-wrap gap-1">
            {alignment.factors_applied.map((f) => (
              <span key={f} className="stat-pill">
                {f.replace(/_/g, ' ')}
              </span>
            ))}
          </div>
        </div>
      )}

      {alignment.alternatives.length > 0 && (
        <div>
          <h3 className="panel-kicker mb-1">Alternatives</h3>
          <div className="space-y-1">
            {alignment.alternatives.map((alt, i) => (
              <div
                key={i}
                className="flex justify-between text-xs rounded-md px-2 py-1.5"
                style={{ border: '1px solid var(--line)' }}
              >
                <span className="font-bold" style={{ color: 'var(--ink)' }}>
                  {alt.shift_type.replace(/_/g, ' ')}
                </span>
                <span style={{ color: 'var(--muted)' }}>
                  OAA {formatSigned(alt.predicted_oaa_delta, 2)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <FielderTable positions={alignment.fielder_positions} />
    </div>
  )
}

function FielderTable({ positions }: { positions: Record<string, import('@/types').FielderPosition> }) {
  const entries = Object.entries(positions)
  if (!entries.length) return null

  return (
    <div>
      <h3 className="panel-kicker mb-1">Positions</h3>
      <table className="w-full text-xs">
        <thead>
          <tr style={{ color: 'var(--muted)', borderBottom: '1px solid var(--line)' }}>
            <th className="text-left py-1 font-bold uppercase text-[10px]">Pos</th>
            <th className="text-left py-1 font-bold uppercase text-[10px]">Player</th>
            <th className="text-right py-1 font-bold uppercase text-[10px]">Depth</th>
            <th className="text-right py-1 font-bold uppercase text-[10px]">Angle</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([pos, fp]) => (
            <tr key={pos} style={{ borderBottom: '1px solid var(--line)' }}>
              <td className="py-1 font-extrabold" style={{ color: 'var(--ink)' }}>{pos}</td>
              <td className="py-1" style={{ color: 'var(--muted)' }}>{fp.player_name}</td>
              <td className="py-1 text-right" style={{ color: 'var(--muted)' }}>{fp.depth_ft}ft</td>
              <td className="py-1 text-right" style={{ color: 'var(--muted)' }}>{fp.angle_deg}°</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function formatSigned(n: number, decimals: number): string {
  const s = n.toFixed(decimals)
  return n > 0 ? `+${s}` : s
}
