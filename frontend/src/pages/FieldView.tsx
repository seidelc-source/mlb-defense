import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FieldCanvas } from '@/components/field/FieldCanvas'
import { ScenarioPanel } from '@/components/panels/ScenarioPanel'
import { AlignmentResults } from '@/components/panels/AlignmentResults'
import { WeatherControls } from '@/components/panels/WeatherControls'
import { useAlignment } from '@/hooks/useAlignment'
import { useAlignmentStore } from '@/stores/alignmentStore'
import { useScenarioStore } from '@/stores/scenarioStore'
import { alignmentApi, stadiumApi, teamApi, weatherApi } from '@/api/alignmentApi'
import type { Point } from '@/lib/fieldCoords'
import type { AlignmentRequest, AlignmentScoreResponse } from '@/types'
import { cn } from '@/lib/cn'

export function FieldView() {
  const scenario = useScenarioStore()
  const { current: alignment, isLoading, error } = useAlignmentStore()
  const alignmentMutation = useAlignment()

  // Custom drag state: position code -> normalized coords
  const [customPositions, setCustomPositions] = useState<Record<string, Point> | null>(null)
  const [customScore, setCustomScore] = useState<AlignmentScoreResponse | null>(null)
  const [scoring, setScoring] = useState(false)
  const scoreTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { data: weather } = useQuery({
    queryKey: ['weather', scenario.stadiumId],
    queryFn: () => weatherApi.current(scenario.stadiumId!),
    enabled: !!scenario.stadiumId,
    staleTime: 10 * 60_000,
    retry: false,
  })

  const { data: parkLayout } = useQuery({
    queryKey: ['stadium-layout', scenario.stadiumId],
    queryFn: () => stadiumApi.layout(scenario.stadiumId!),
    enabled: !!scenario.stadiumId,
    staleTime: Infinity,
  })

  const { data: teams } = useQuery({
    queryKey: ['teams'],
    queryFn: teamApi.list,
    staleTime: Infinity,
  })

  const battingTeam = teams?.find((t) => t.id === scenario.battingTeamId)
  const fieldingTeam = teams?.find((t) => t.id === scenario.teamId)

  const { data: history, refetch: refetchHistory } = useQuery({
    queryKey: ['alignment-history', scenario.batterId],
    queryFn: () => alignmentApi.getHistory({ batter_id: scenario.batterId!, limit: 8 }),
    enabled: !!scenario.batterId,
    staleTime: 30_000,
  })

  // Clear custom drag state whenever a fresh recommendation arrives
  useEffect(() => {
    setCustomPositions(null)
    setCustomScore(null)
  }, [alignment?.alignment_id])

  const handleRequestAlignment = useCallback(() => {
    if (!scenario.batterId || !scenario.pitcherId || !scenario.teamId || !scenario.stadiumId) return

    const req: AlignmentRequest = {
      team_id: scenario.teamId,
      batter_id: scenario.batterId,
      pitcher_id: scenario.pitcherId,
      stadium_id: scenario.stadiumId,
      weather_id: scenario.weatherId ?? undefined,
      weather: scenario.weather.enabled
        ? {
            temperature_f: scenario.weather.temperature_f,
            humidity_pct: scenario.weather.humidity_pct,
            wind_speed_mph: scenario.weather.wind_speed_mph,
            wind_direction_deg: scenario.weather.wind_direction_deg,
          }
        : undefined,
      inning: scenario.inning,
      outs: scenario.outs,
      runners: scenario.runners,
      score_diff: scenario.scoreDiff,
      active_roster: scenario.activeRoster.map((r) => ({
        player_id: r.player_id,
        position: r.position,
      })),
      optimize_for: scenario.optimizeFor,
      include_factors: ['pitcher_type', 'batter_spray', 'weather', 'injury', 'stadium'],
    }

    alignmentMutation.mutate(req, { onSuccess: () => refetchHistory() })
  }, [scenario, alignmentMutation, refetchHistory])

  // Drag a fielder → merge into custom positions → debounce-score
  const handleFielderDrag = useCallback(
    (positionCode: string, norm: Point) => {
      if (!alignment || !scenario.batterId) return

      const base: Record<string, Point> = {}
      for (const [pos, fp] of Object.entries(alignment.fielder_positions)) {
        base[pos] = customPositions?.[pos] ?? { x: fp.x, y: fp.y }
      }
      base[positionCode] = {
        x: Math.max(0, Math.min(1, norm.x)),
        y: Math.max(0, Math.min(1, norm.y)),
      }
      setCustomPositions(base)

      if (scoreTimer.current) clearTimeout(scoreTimer.current)
      setScoring(true)
      scoreTimer.current = setTimeout(async () => {
        try {
          const result = await alignmentApi.score({
            batter_id: scenario.batterId!,
            positions: Object.fromEntries(
              Object.entries(base).map(([k, v]) => [k, { x: v.x, y: v.y }])
            ),
            active_roster: scenario.activeRoster,
            stadium_id: scenario.stadiumId ?? undefined,
            optimize_for: scenario.optimizeFor,
          })
          setCustomScore(result)
        } catch {
          setCustomScore(null)
        } finally {
          setScoring(false)
        }
      }, 350)
    },
    [alignment, customPositions, scenario.batterId, scenario.activeRoster, scenario.optimizeFor]
  )

  const resetCustom = useCallback(() => {
    setCustomPositions(null)
    setCustomScore(null)
  }, [])

  // Swap batting and fielding sides; batter/pitcher belong to specific teams
  // so they reset, and the park follows the new fielding team home.
  const swapSides = useCallback(() => {
    const s = useScenarioStore.getState()
    const oldBatting = s.battingTeamId
    const oldFielding = s.teamId
    if (!oldBatting && !oldFielding) return
    if (oldFielding) s.setBattingTeam(oldFielding)
    if (oldBatting) {
      s.setTeam(oldBatting)
      const home = teams?.find((t) => t.id === oldBatting)?.home_stadium_id
      if (home) s.setStadium(home)
    }
    s.setBatter('')
    s.setPitcher('')
    s.setRoster([])
  }, [teams])

  // Re-load a past recommendation onto the field. History rows carry raw
  // positions, so rebuild a displayable AlignmentResponse client-side.
  const loadHistoryItem = useCallback((item: import('@/types').AlignmentHistoryItem) => {
    if (!item.fielder_positions) return
    const fielder_positions: Record<string, import('@/types').FielderPosition> = {}
    for (const [pos, coords] of Object.entries(item.fielder_positions)) {
      if (pos === 'C' || pos === 'P') continue
      const [x, y] = coords as unknown as [number, number]
      fielder_positions[pos] = {
        player_id: pos,
        player_name: pos,
        x,
        y,
        depth_ft: Math.round(y * 400),
        angle_deg: Math.round((x - 0.5) * 90 * 10) / 10,
        catch_prob_zone: 0,
      }
    }
    useAlignmentStore.getState().setCurrent({
      alignment_id: item.id,
      shift_type: item.shift_type,
      fielder_positions,
      coverage_map: [],
      overlap_zones: [],
      predicted_oaa_delta: item.predicted_oaa_delta ?? 0,
      predicted_hit_pct: item.predicted_hit_pct ?? 0,
      predicted_out_pct: item.predicted_hit_pct != null ? 1 - item.predicted_hit_pct : 0,
      confidence: item.confidence ?? 0,
      optimize_for: item.optimize_for,
      factors_applied: [],
      alternatives: [],
      created_at: item.created_at,
    })
  }, [])

  return (
    <div className="flex flex-col lg:flex-row h-full gap-4 p-4 overflow-y-auto lg:overflow-hidden" style={{ background: 'transparent' }}>
      {/* left rail: scenario controls */}
      <aside className="w-full lg:w-72 shrink-0 panel overflow-hidden !p-0">
        <ScenarioPanel onRequestAlignment={handleRequestAlignment} />
      </aside>

      {/* center: matchup header + field + custom score strip */}
      <div className="flex-1 flex flex-col items-center min-w-0 gap-3">
        {(battingTeam || fieldingTeam) && (
          <div className="panel w-full max-w-[680px] flex flex-wrap items-center gap-x-3 gap-y-1 !py-2">
            <span className="text-sm font-extrabold" style={{ color: 'var(--ink)' }}>
              {battingTeam?.abbreviation ?? '—'} @ {fieldingTeam?.abbreviation ?? '—'}
            </span>
            <button
              onClick={swapSides}
              title="Swap batting and fielding sides"
              className="btn-chip !min-h-[22px] !px-1.5 text-[11px]"
            >
              ⇄
            </button>
            {parkLayout && (
              <span className="text-xs font-bold" style={{ color: 'var(--muted)' }}>
                {parkLayout.name}
              </span>
            )}
            {parkLayout && (
              <span className="stat-pill !py-0.5">{parkLayout.roof_type} roof</span>
            )}
            {weather?.temperature_f != null && (
              <span className="stat-pill !py-0.5">{Math.round(weather.temperature_f)}°F</span>
            )}
            <span className="text-[11px] ml-auto" style={{ color: 'var(--muted)' }}>
              {battingTeam ? `${battingTeam.name} batting` : ''}
            </span>
          </div>
        )}
        {customScore && (
          <CustomScoreBar score={customScore} baseline={alignment} scoring={scoring} onReset={resetCustom} />
        )}
        <div className="w-full flex-1 min-h-0 flex items-start justify-center">
          <div className="w-full h-full max-w-[680px]">
            <FieldCanvas
              alignment={alignment}
              layout={parkLayout ?? null}
              customPositions={customPositions}
              illegalPositions={customScore?.illegal_positions ?? []}
              weather={weather ?? null}
              onFielderDrag={handleFielderDrag}
            />
          </div>
        </div>
      </div>

      {/* right rail: results + weather + history */}
      <aside className="w-full lg:w-72 shrink-0 flex flex-col gap-3 lg:overflow-y-auto">
        <div className="panel !p-0">
          <AlignmentResults alignment={alignment} isLoading={isLoading} error={error} />
        </div>
        <WeatherControls stadiumId={scenario.stadiumId} liveWeather={weather ?? null} />
        {history && history.length > 0 && (
          <HistoryPanel items={history} onLoad={loadHistoryItem} />
        )}
      </aside>
    </div>
  )
}

function CustomScoreBar({
  score,
  baseline,
  scoring,
  onReset,
}: {
  score: AlignmentScoreResponse
  baseline: import('@/types').AlignmentResponse | null
  scoring: boolean
  onReset: () => void
}) {
  const deltaVsRec = baseline ? score.predicted_oaa_delta - baseline.predicted_oaa_delta : null

  return (
    <div className="panel w-full max-w-[680px] flex flex-wrap items-center gap-x-4 gap-y-1 !py-2 min-w-0">
      <span className="panel-kicker shrink-0">Custom</span>

      <Stat
        label="vs std"
        value={signed(score.predicted_oaa_delta)}
        tone={score.predicted_oaa_delta >= 0 ? 'good' : 'bad'}
      />
      {deltaVsRec != null && (
        <Stat
          label="vs rec"
          value={signed(deltaVsRec)}
          tone={deltaVsRec >= -0.0001 ? 'good' : 'bad'}
        />
      )}
      <Stat label="out" value={`${(score.predicted_out_pct * 100).toFixed(1)}%`} />

      {!score.legal && (
        <span
          className="text-[11px] font-bold px-2 py-0.5 rounded shrink-0"
          style={{ background: 'rgba(155,47,47,0.12)', color: 'var(--danger)' }}
        >
          Illegal: {score.illegal_positions.join(', ')}
        </span>
      )}

      {scoring && <span className="text-xs shrink-0" style={{ color: 'var(--muted)' }}>scoring…</span>}

      <button onClick={onReset} className="btn-chip ml-auto shrink-0 !min-h-[24px] !px-2 text-[11px]">
        Reset
      </button>
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'good' | 'bad' }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span
        className={cn('text-sm font-extrabold')}
        style={{
          color: tone === 'good' ? 'var(--ok)' : tone === 'bad' ? 'var(--danger)' : 'var(--ink)',
        }}
      >
        {value}
      </span>
      <span className="text-[10px] uppercase font-bold" style={{ color: 'var(--muted)' }}>
        {label}
      </span>
    </div>
  )
}

function HistoryPanel({
  items,
  onLoad,
}: {
  items: import('@/types').AlignmentHistoryItem[]
  onLoad: (item: import('@/types').AlignmentHistoryItem) => void
}) {
  return (
    <div className="panel">
      <h3 className="panel-kicker mb-2">Recent recommendations</h3>
      <div className="space-y-1.5">
        {items.map((item) => (
          <button
            key={item.id}
            onClick={() => onLoad(item)}
            disabled={!item.fielder_positions}
            title="Load this alignment onto the field"
            className="w-full flex items-center justify-between text-xs rounded-md px-2 py-1.5 hover:brightness-95"
            style={{ border: '1px solid var(--line)', background: '#fff' }}
          >
            <span className="font-bold" style={{ color: 'var(--ink)' }}>
              {item.shift_type.replace(/_/g, ' ')}
            </span>
            <span style={{ color: 'var(--muted)' }}>
              {item.predicted_oaa_delta != null ? signed(item.predicted_oaa_delta) : '—'} ·{' '}
              {new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}

function signed(n: number): string {
  const s = n.toFixed(3)
  return n > 0 ? `+${s}` : s
}
