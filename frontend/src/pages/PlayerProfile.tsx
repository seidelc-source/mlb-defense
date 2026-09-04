import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PlayerPicker } from '@/components/ui/PlayerPicker'
import { EmptyState, LoadingState, ErrorState } from '@/components/ui/StatusStates'
import { usePlayer, usePlayerRange } from '@/hooks/useSpray'
import { playerApi } from '@/api/playerApi'
import { teamApi } from '@/api/alignmentApi'
import { cn } from '@/lib/cn'
import { mergeSeasons } from '@/lib/seasons'
import { IS_DEMO } from '@/lib/demo'
import type { FieldingProfile, InjuryCreate, PitcherProfile } from '@/types'

export function PlayerProfile() {
  const [playerId, setPlayerId] = useState<string | null>(null)
  const [teamId, setTeamId] = useState<string | null>(null)
  const [season, setSeason] = useState(2024)

  const { data: teams } = useQuery({
    queryKey: ['teams'],
    queryFn: teamApi.list,
    staleTime: Infinity,
  })

  const { data: player, isLoading: playerLoading } = usePlayer(playerId)

  // Offer seasons that have fielding OR pitching data for this player
  const { data: fieldingSeasons } = useQuery({
    queryKey: ['fielding-seasons', playerId],
    queryFn: () => playerApi.getFieldingSeasons(playerId!),
    enabled: !!playerId,
    staleTime: 5 * 60_000,
  })
  const { data: pitchingSeasons } = useQuery({
    queryKey: ['pitching-seasons', playerId],
    queryFn: () => playerApi.getPitchingSeasons(playerId!),
    enabled: !!playerId,
    staleTime: 5 * 60_000,
  })

  const seasons = useMemo(
    () => mergeSeasons(fieldingSeasons, pitchingSeasons),
    [fieldingSeasons, pitchingSeasons],
  )

  useEffect(() => {
    if (seasons.length && !seasons.includes(season)) {
      setSeason(seasons[0])
    }
  }, [seasons, season])

  const { data: fielding, isLoading: fieldingLoading, error: fieldingError } = useQuery({
    queryKey: ['fielding', playerId, season],
    queryFn: () => playerApi.getFielding(playerId!, season),
    enabled: !!playerId,
    staleTime: 5 * 60_000,
  })

  // Only fetch a pitcher profile when the selected season actually has one
  const { data: pitching } = useQuery({
    queryKey: ['pitching', playerId, season],
    queryFn: () => playerApi.getPitching(playerId!, season),
    enabled: !!playerId && (pitchingSeasons?.includes(season) ?? false),
    staleTime: 5 * 60_000,
    retry: false,
  })

  const { data: range } = usePlayerRange(playerId, player?.position)

  return (
    <div className="flex flex-col h-full p-6 overflow-y-auto">
      <div className="flex items-end gap-4 mb-6 flex-wrap">
        <label className="text-xs text-[color:var(--muted)] w-56">
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
          label="Player"
          value={playerId}
          onSelect={setPlayerId}
          teamId={teamId}
          className="w-72"
        />
        <label className="text-xs text-[color:var(--muted)]">
          Season
          <select
            value={season}
            onChange={(e) => setSeason(Number(e.target.value))}
            className="block mt-0.5"
            disabled={!playerId || !seasons.length}
          >
            {(seasons.length ? seasons : [2024]).map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </label>
      </div>

      {!playerId && <EmptyState message="Select a player to view their profile." />}

      {playerLoading && <LoadingState message="Loading player..." />}

      {player && (
        <div className="space-y-6">
          {/* Player header */}
          <div className="panel !p-5">
            <h2 className="text-lg font-semibold text-[color:var(--ink)]">{player.full_name}</h2>
            <div className="flex gap-4 mt-1 text-sm text-[color:var(--muted)]">
              <span>{player.position}</span>
              <span>Bats: {player.bats}</span>
              <span>Throws: {player.throws}</span>
              {player.birth_date && <span>DOB: {player.birth_date}</span>}
              <span className={player.active ? 'text-[color:var(--ok)]' : 'text-[color:var(--danger)]'}>
                {player.active ? 'Active' : 'Inactive'}
              </span>
            </div>
            <div className="flex gap-3 mt-2 text-xs text-[color:var(--muted)]">
              {player.mlbam_id && <span>MLBAM: {player.mlbam_id}</span>}
              {player.fangraphs_id && <span>FG: {player.fangraphs_id}</span>}
              {player.bbref_id && <span>BBRef: {player.bbref_id}</span>}
            </div>
          </div>

          {/* Pitching profile (pitchers only) */}
          {pitching && <PitcherCard profile={pitching} />}

          {/* Fielding profiles */}
          {fieldingLoading && <LoadingState message="Loading fielding data..." />}
          {fieldingError && <ErrorState message={(fieldingError as Error).message} />}

          {fielding && fielding.length > 0 && (
            <div className="panel !p-5">
              <h3 className="text-sm font-semibold text-[color:var(--ink)] uppercase tracking-wider mb-3">
                Fielding Profiles — {season}
              </h3>
              <div className="space-y-4">
                {fielding.map((fp, i) => (
                  <FieldingCard key={i} profile={fp} />
                ))}
              </div>
            </div>
          )}

          {fielding && fielding.length === 0 && (
            <EmptyState message={`No fielding data for ${season}.`} />
          )}

          {/* Range data */}
          {range && (
            <div className="panel !p-5">
              <h3 className="text-sm font-semibold text-[color:var(--ink)] uppercase tracking-wider mb-3">
                Range & Arm
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
                <RangeStat label="0.75s reach" value={`${range.radii.zone_075s} ft`} />
                <RangeStat label="1.25s reach" value={`${range.radii.zone_125s} ft`} />
                <RangeStat label="1.75s reach" value={`${range.radii.zone_175s} ft`} />
                <RangeStat label="2.25s reach" value={`${range.radii.zone_225s} ft`} />
                <RangeStat label="3.0s reach" value={`${range.radii.zone_300s} ft`} />
              </div>
              <div className="grid grid-cols-2 gap-3 mt-3">
                <RangeStat label="Max throw" value={`${range.arm_throw_range.max_distance_ft} ft`} />
                <RangeStat label="Throw accuracy" value={`${(range.arm_throw_range.accuracy_pct * 100).toFixed(0)}%`} />
              </div>
              {range.injury_adjusted && (
                <p className="text-xs text-[#8a6116] mt-2">Values adjusted for active injuries</p>
              )}
            </div>
          )}

          {/* Injury management */}
          <InjuryPanel playerId={playerId!} />
        </div>
      )}
    </div>
  )
}

function InjuryPanel({ playerId }: { playerId: string }) {
  const queryClient = useQueryClient()
  const [bodyPart, setBodyPart] = useState('')
  const [severity, setSeverity] = useState<InjuryCreate['severity']>('moderate')
  const [notes, setNotes] = useState('')

  const { data: injuries } = useQuery({
    queryKey: ['injuries', playerId],
    queryFn: () => playerApi.getInjuries(playerId),
    staleTime: 30_000,
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['injuries', playerId] })
    queryClient.invalidateQueries({ queryKey: ['fielding'] })
    queryClient.invalidateQueries({ queryKey: ['range'] })
  }

  const addMutation = useMutation({
    mutationFn: (body: InjuryCreate) => playerApi.addInjury(playerId, body),
    onSuccess: () => {
      setBodyPart('')
      setNotes('')
      invalidate()
    },
  })

  const endMutation = useMutation({
    mutationFn: (injuryId: string) => playerApi.endInjury(playerId, injuryId),
    onSuccess: invalidate,
  })

  return (
    <div className="panel !p-5">
      <h3 className="text-sm font-semibold text-[color:var(--ink)] uppercase tracking-wider mb-3">
        Injuries
      </h3>

      {(injuries ?? []).length === 0 && (
        <p className="text-xs mb-3" style={{ color: 'var(--muted)' }}>
          No active injuries. Adding one degrades the player's speed, range,
          and arm in every alignment until it's marked healed.
          {IS_DEMO && ' Injury editing needs the live engine — run the app locally.'}
        </p>
      )}

      {IS_DEMO ? null : (
      <>


      {(injuries ?? []).map((inj) => (
        <div
          key={inj.id}
          className="flex items-center gap-2 text-xs rounded-md px-3 py-2 mb-2"
          style={{ border: '1px solid var(--line)' }}
        >
          <span
            className={cn(
              'px-1.5 py-0.5 rounded text-[10px] font-bold uppercase',
              inj.severity === 'severe'
                ? 'bg-[#f6e3e3] text-[color:var(--danger)]'
                : inj.severity === 'moderate'
                  ? 'bg-[#f7ecd9] text-[#8a6116]'
                  : 'bg-[#edf1ea] text-[color:var(--muted)]'
            )}
          >
            {inj.severity}
          </span>
          <span className="font-bold" style={{ color: 'var(--ink)' }}>{inj.body_part}</span>
          {inj.start_date && (
            <span style={{ color: 'var(--muted)' }}>since {inj.start_date}</span>
          )}
          <span className="ml-auto" style={{ color: 'var(--muted)' }}>
            spd ×{inj.speed_factor.toFixed(2)} · rng ×{inj.range_factor.toFixed(2)} · arm ×{inj.arm_strength_factor.toFixed(2)}
          </span>
          <button
            onClick={() => endMutation.mutate(inj.id)}
            disabled={endMutation.isPending}
            className="btn-chip !min-h-[24px] !px-2 text-[11px]"
          >
            Mark healed
          </button>
        </div>
      ))}

      <div className="flex items-end gap-2 flex-wrap mt-3">
        <label className="text-xs" style={{ color: 'var(--muted)' }}>
          Body part
          <input
            type="text"
            value={bodyPart}
            onChange={(e) => setBodyPart(e.target.value)}
            placeholder="hamstring, shoulder…"
            className="block w-44 mt-0.5"
          />
        </label>
        <label className="text-xs" style={{ color: 'var(--muted)' }}>
          Severity
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value as InjuryCreate['severity'])}
            className="block w-32 mt-0.5"
          >
            <option value="mild">mild</option>
            <option value="moderate">moderate</option>
            <option value="severe">severe</option>
          </select>
        </label>
        <label className="text-xs flex-1 min-w-[140px]" style={{ color: 'var(--muted)' }}>
          Notes
          <input
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="block w-full mt-0.5"
          />
        </label>
        <button
          onClick={() =>
            addMutation.mutate({ body_part: bodyPart.trim(), severity, notes: notes || undefined })
          }
          disabled={bodyPart.trim().length < 2 || addMutation.isPending}
          className="btn-primary !py-1.5"
        >
          Add injury
        </button>
      </div>
      {addMutation.isError && (
        <p className="text-xs mt-2" style={{ color: 'var(--danger)' }}>
          {(addMutation.error as Error).message}
        </p>
      )}
      </>
      )}
    </div>
  )
}

export function PitcherCard({ profile: pp }: { profile: PitcherProfile }) {
  const pct = (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)
  const mph = (v: number | null) => (v == null ? '—' : `${v} mph`)
  const mix = Object.entries(pp.pitch_mix ?? {})

  return (
    <div className="panel !p-5">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h3 className="text-sm font-semibold text-[color:var(--ink)] uppercase tracking-wider">
          Pitching Profile — {pp.season}
        </h3>
        <div className="flex gap-2">
          <span className="stat-pill">{pp.role}</span>
          <span className="stat-pill capitalize">{pp.pitcher_type}</span>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-2">
        <PitchStat label="Avg velo" value={mph(pp.avg_velocity_mph)} />
        <PitchStat label="Fastball" value={mph(pp.avg_fastball_mph)} />
        <PitchStat label="Max FB" value={mph(pp.max_fastball_mph)} />
        <PitchStat label="Spin" value={pp.spin_rate_avg == null ? '—' : `${pp.spin_rate_avg} rpm`} />
      </div>

      <div className="grid grid-cols-3 sm:grid-cols-6 gap-x-6 gap-y-2 mt-3 pt-3 border-t border-[color:var(--line)]">
        <PitchStat label="GB" value={pct(pp.groundball_pct)} />
        <PitchStat label="FB" value={pct(pp.flyball_pct)} />
        <PitchStat label="LD" value={pct(pp.linedrive_pct)} />
        <PitchStat label="PU" value={pct(pp.popup_pct)} />
        <PitchStat label="K" value={pct(pp.strikeout_pct)} />
        <PitchStat label="BB" value={pct(pp.walk_pct)} />
      </div>

      {mix.length > 0 && (
        <div className="mt-3 pt-3 border-t border-[color:var(--line)]">
          <span className="text-[10px] text-[color:var(--muted)] uppercase">Pitch mix</span>
          <div className="space-y-1 mt-1">
            {mix.map(([type, share]) => (
              <div key={type} className="flex items-center gap-2 text-xs">
                <span className="w-9 font-medium text-[color:var(--ink)]">{type}</span>
                <div className="flex-1 h-3 bg-[#e6ebe1] rounded overflow-hidden">
                  <div
                    className="h-full bg-[color:var(--clay)]"
                    style={{ width: `${Math.round(share * 100)}%` }}
                  />
                </div>
                <span className="w-9 text-right text-[color:var(--muted)]">
                  {Math.round(share * 100)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function PitchStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-xs">
      <span className="text-[color:var(--muted)]">{label}</span>
      <span className="text-[color:var(--ink)]">{value}</span>
    </div>
  )
}

function FieldingCard({ profile: fp }: { profile: FieldingProfile }) {
  return (
    <div className="border border-[color:var(--line)] rounded p-4">
      <div className="flex justify-between items-baseline mb-3">
        <span className="text-sm font-medium text-[color:var(--ink)]">{fp.position}</span>
        <span className="text-xs text-[color:var(--muted)]">
          {fp.games}G · {fp.innings}IP
          {fp.injury_adjusted && <span className="text-[#8a6116] ml-2">injury adj.</span>}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-x-6 gap-y-2">
        <MetricRow label="OAA" value={fp.outs_above_average} format="signed" />
        <MetricRow label="FRV" value={fp.fielding_run_value} format="signed" />
        <MetricRow label="Sprint" value={fp.sprint_speed_ft_s} suffix=" ft/s" />
        <MetricRow label="Sprint lvl" value={fp.sprint_speed_level} />
        <MetricRow label="Reaction" value={fp.reaction_time_s} suffix="s" />
        <MetricRow label="Route eff" value={fp.route_efficiency_pct} suffix="%" />
        <MetricRow label="Arm str" value={fp.arm_strength_mph} suffix=" mph" />
        <MetricRow label="Arm acc" value={fp.arm_accuracy_pct} suffix="%" />
      </div>

      {(fp.oaa_back !== null || fp.oaa_in !== null) && (
        <div className="mt-3 pt-2 border-t border-[color:var(--line)]">
          <span className="text-[10px] text-[color:var(--muted)] uppercase">OAA breakdown</span>
          <div className="flex gap-4 mt-1">
            <OaaSplit label="Back" value={fp.oaa_back} />
            <OaaSplit label="In" value={fp.oaa_in} />
            <OaaSplit label="Left" value={fp.oaa_left} />
            <OaaSplit label="Right" value={fp.oaa_right} />
          </div>
        </div>
      )}

      {fp.injury_factors && fp.injury_factors.length > 0 && (
        <div className="mt-3 pt-2 border-t border-[color:var(--line)]">
          <span className="text-[10px] text-[color:var(--muted)] uppercase">Active injuries</span>
          <div className="space-y-1 mt-1">
            {fp.injury_factors.map((inj, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className={cn(
                  'px-1.5 py-0.5 rounded text-[10px] font-medium',
                  inj.severity === 'severe' ? 'bg-[#f6e3e3] text-[color:var(--danger)]' :
                  inj.severity === 'moderate' ? 'bg-[#f7ecd9] text-[#8a6116]' :
                  'bg-[#edf1ea] text-[color:var(--muted)]'
                )}>
                  {inj.severity}
                </span>
                <span className="text-[color:var(--muted)]">{inj.body_part}</span>
                <span className="text-[color:var(--muted)] ml-auto">
                  spd {inj.speed_factor.toFixed(2)} · rng {inj.range_factor.toFixed(2)} · arm {inj.arm_strength_factor.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function MetricRow({
  label,
  value,
  suffix = '',
  format,
}: {
  label: string
  value: number | null
  suffix?: string
  format?: 'signed'
}) {
  if (value === null) return null
  const display = format === 'signed' && value > 0 ? `+${value.toFixed(1)}` : `${value}`
  return (
    <div className="flex justify-between text-xs">
      <span className="text-[color:var(--muted)]">{label}</span>
      <span className={cn(
        'text-[color:var(--ink)]',
        format === 'signed' && value > 0 && 'text-[color:var(--ok)]',
        format === 'signed' && value < 0 && 'text-[color:var(--danger)]',
      )}>
        {display}{suffix}
      </span>
    </div>
  )
}

function OaaSplit({ label, value }: { label: string; value: number | null }) {
  if (value === null) return null
  return (
    <div className="text-xs">
      <span className="text-[color:var(--muted)]">{label} </span>
      <span className={cn(
        value > 0 ? 'text-[color:var(--ok)]' : value < 0 ? 'text-[color:var(--danger)]' : 'text-[color:var(--muted)]'
      )}>
        {value > 0 ? '+' : ''}{value}
      </span>
    </div>
  )
}

function RangeStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-[#edf1ea] rounded px-3 py-2">
      <div className="text-[10px] text-[color:var(--muted)] uppercase">{label}</div>
      <div className="text-sm text-[color:var(--ink)] font-medium mt-0.5">{value}</div>
    </div>
  )
}
