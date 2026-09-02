import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PlayerPicker } from '@/components/ui/PlayerPicker'
import { SprayChart } from '@/components/charts/SprayChart'
import { useSpray } from '@/hooks/useSpray'
import { teamApi } from '@/api/alignmentApi'
import { playerApi } from '@/api/playerApi'
import { cn } from '@/lib/cn'
import type { SprayParams } from '@/api/playerApi'

const PITCH_TYPES = ['All', 'FF', 'SI', 'SL', 'CH', 'CU', 'FC', 'KC', 'FS']
const PITCHER_HANDS = ['All', 'R', 'L']
// Bands must match the backend aggregation (SPEED_BANDS in spray_aggregate.py)
const SPEED_BANDS: Array<{ label: string; min?: number; max?: number }> = [
  { label: 'All' },
  { label: '<90', min: 0, max: 90 },
  { label: '90+', min: 90, max: 110 },
]

export function SprayAnalysis() {
  const [batterId, setBatterId] = useState<string | null>(null)
  const [teamId, setTeamId] = useState<string | null>(null)
  const [pitchType, setPitchType] = useState('All')
  const [pitcherHand, setPitcherHand] = useState('All')
  const [speedBand, setSpeedBand] = useState('All')
  const [season, setSeason] = useState(2024)

  const { data: teams } = useQuery({
    queryKey: ['teams'],
    queryFn: teamApi.list,
    staleTime: Infinity,
  })

  // Only offer seasons that actually have spray data, plus "Total"
  const { data: seasons } = useQuery({
    queryKey: ['spray-seasons', batterId],
    queryFn: () => playerApi.getSpraySeasons(batterId!),
    enabled: !!batterId,
    staleTime: 5 * 60_000,
  })

  useEffect(() => {
    if (!seasons) return
    // season 0 = Total; otherwise snap to the newest available season
    if (season !== 0 && !seasons.includes(season)) {
      setSeason(seasons[0] ?? 0)
    }
  }, [seasons, season])

  const band = SPEED_BANDS.find((b) => b.label === speedBand)
  const params: SprayParams = {
    season,
    ...(pitchType !== 'All' && { pitch_type: pitchType }),
    ...(pitcherHand !== 'All' && { pitcher_hand: pitcherHand }),
    ...(band?.min !== undefined && { speed_min: band.min, speed_max: band.max }),
  }

  const { data, isLoading, error } = useSpray(batterId, params)

  return (
    <div className="flex flex-col h-full p-6 overflow-y-auto">
      <div className="flex items-end gap-4 mb-6 flex-wrap">
        <label className="text-xs text-[color:var(--muted)] w-52">
          Team
          <select
            value={teamId ?? ''}
            onChange={(e) => setTeamId(e.target.value || null)}
            className="block w-full mt-0.5"
          >
            <option value="">All teams</option>
            {(teams ?? []).map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </label>
        <PlayerPicker
          label="Batter"
          value={batterId}
          onSelect={setBatterId}
          teamId={teamId}
          role="batter"
          className="w-64"
        />

        <label className="text-xs text-[color:var(--muted)]">
          Season
          <select
            value={season}
            onChange={(e) => setSeason(Number(e.target.value))}
            className="block mt-0.5"
            disabled={!batterId || !seasons?.length}
          >
            {(seasons ?? [2024]).map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
            {(seasons?.length ?? 0) > 0 && <option value={0}>Total</option>}
          </select>
        </label>

        <div>
          <span className="text-xs text-[color:var(--muted)] block mb-1">Pitch Type</span>
          <div className="flex gap-0.5">
            {PITCH_TYPES.map((pt) => (
              <button
                key={pt}
                onClick={() => setPitchType(pt)}
                className={cn(
                  'px-2 py-1 text-xs rounded',
                  pitchType === pt
                    ? 'bg-[#f2dfc9] text-[color:var(--clay-dark)] border border-[color:var(--clay)] font-bold'
                    : 'bg-white text-[color:var(--muted)] border border-[color:var(--line)] hover:bg-[#edf1ea]'
                )}
              >
                {pt}
              </button>
            ))}
          </div>
        </div>

        <div>
          <span className="text-xs text-[color:var(--muted)] block mb-1">Pitcher Hand</span>
          <div className="flex gap-0.5">
            {PITCHER_HANDS.map((h) => (
              <button
                key={h}
                onClick={() => setPitcherHand(h)}
                className={cn(
                  'px-2 py-1 text-xs rounded',
                  pitcherHand === h
                    ? 'bg-[#f2dfc9] text-[color:var(--clay-dark)] border border-[color:var(--clay)] font-bold'
                    : 'bg-white text-[color:var(--muted)] border border-[color:var(--line)] hover:bg-[#edf1ea]'
                )}
              >
                {h}
              </button>
            ))}
          </div>
        </div>

        <div>
          <span className="text-xs text-[color:var(--muted)] block mb-1">Pitch Speed</span>
          <div className="flex gap-0.5">
            {SPEED_BANDS.map((b) => (
              <button
                key={b.label}
                onClick={() => setSpeedBand(b.label)}
                className={cn(
                  'px-2 py-1 text-xs rounded',
                  speedBand === b.label
                    ? 'bg-[#f2dfc9] text-[color:var(--clay-dark)] border border-[color:var(--clay)] font-bold'
                    : 'bg-white text-[color:var(--muted)] border border-[color:var(--line)] hover:bg-[#edf1ea]'
                )}
              >
                {b.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1">
        {!batterId && (
          <div className="text-[color:var(--muted)] text-sm">Select a batter to view their spray chart.</div>
        )}

        {isLoading && (
          <div className="text-[color:var(--muted)] text-sm animate-pulse">Loading spray data...</div>
        )}

        {error && (
          <div className="text-[color:var(--danger)] text-sm">{friendlyError(error)}</div>
        )}

        {data && <SprayChart data={data} />}
      </div>
    </div>
  )
}

function friendlyError(error: unknown): string {
  const axiosErr = error as { response?: { status?: number; data?: { detail?: string } } }
  const status = axiosErr.response?.status
  const detail = axiosErr.response?.data?.detail
  if (status === 404) return 'No batted-ball data for this batter and filter combination.'
  if (status === 422 && detail) return detail
  return detail ?? (error as Error).message
}
