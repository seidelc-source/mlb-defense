import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useScenarioStore } from '@/stores/scenarioStore'
import { PlayerPicker } from '@/components/ui/PlayerPicker'
import { teamApi, stadiumApi } from '@/api/alignmentApi'
import { cn } from '@/lib/cn'

const FIELD_POSITIONS = ['1B', '2B', 'SS', '3B', 'LF', 'CF', 'RF']

export function ScenarioPanel({ onRequestAlignment }: { onRequestAlignment: () => void }) {
  const store = useScenarioStore()
  const canRequest = !!store.batterId && !!store.pitcherId && !!store.teamId && !!store.stadiumId

  const { data: teams } = useQuery({
    queryKey: ['teams'],
    queryFn: teamApi.list,
    staleTime: Infinity,
  })

  const { data: stadiums } = useQuery({
    queryKey: ['stadiums'],
    queryFn: stadiumApi.list,
    staleTime: Infinity,
  })

  // When a defensive team is picked, auto-fill the roster with one
  // player per position so the engine uses real fielding profiles.
  const { data: roster } = useQuery({
    queryKey: ['roster', store.teamId],
    queryFn: () => teamApi.roster(store.teamId!),
    enabled: !!store.teamId,
    staleTime: 5 * 60_000,
  })

  useEffect(() => {
    if (!roster) return
    const entries: Array<{ player_id: string; position: string }> = []
    for (const pos of FIELD_POSITIONS) {
      const player = roster.find((p) => p.position === pos)
      if (player) entries.push({ player_id: player.id, position: pos })
    }
    useScenarioStore.getState().setRoster(entries)
  }, [roster])

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      <h2 className="panel-kicker">Scenario</h2>

      <Section title="Batting">
        <label className="text-xs" style={{ color: 'var(--muted)' }}>
          Batting team
          <select
            value={store.battingTeamId ?? ''}
            onChange={(e) => store.setBattingTeam(e.target.value)}
            className="block w-full mt-0.5"
          >
            <option value="">Any team</option>
            {(teams ?? []).map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </label>
        <PlayerPicker
          label="Batter"
          value={store.batterId}
          onSelect={store.setBatter}
          teamId={store.battingTeamId}
          role="batter"
        />
      </Section>

      <Section title="Defense">
        <label className="text-xs" style={{ color: 'var(--muted)' }}>
          Fielding team
          <select
            value={store.teamId ?? ''}
            onChange={(e) => {
              store.setTeam(e.target.value)
              // Auto-sync ballpark to the fielding team's home park;
              // user can still override via the Ballpark select.
              const team = (teams ?? []).find((t) => t.id === e.target.value)
              if (team?.home_stadium_id) store.setStadium(team.home_stadium_id)
            }}
            className="block w-full mt-0.5"
          >
            <option value="" disabled>Select team…</option>
            {(teams ?? []).map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </label>
        <PlayerPicker
          label="Pitcher"
          value={store.pitcherId}
          onSelect={store.setPitcher}
          teamId={store.teamId}
          role="pitcher"
        />
        <label className="text-xs" style={{ color: 'var(--muted)' }}>
          Ballpark
          <select
            value={store.stadiumId ?? ''}
            onChange={(e) => store.setStadium(e.target.value)}
            className="block w-full mt-0.5"
          >
            <option value="" disabled>Select ballpark…</option>
            {(stadiums ?? []).map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </label>
        {store.activeRoster.length > 0 && (
          <p className="text-[11px]" style={{ color: 'var(--muted)' }}>
            {store.activeRoster.length} fielders auto-assigned from roster
          </p>
        )}
      </Section>

      <Section title="Game State">
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs" style={{ color: 'var(--muted)' }}>
            Inning
            <select
              value={store.inning}
              onChange={(e) => store.setInning(Number(e.target.value))}
              className="block w-full mt-0.5"
            >
              {Array.from({ length: 9 }, (_, i) => (
                <option key={i + 1} value={i + 1}>{i + 1}</option>
              ))}
            </select>
          </label>
          <label className="text-xs" style={{ color: 'var(--muted)' }}>
            Outs
            <div className="flex gap-1 mt-1">
              {[0, 1, 2].map((n) => (
                <button
                  key={n}
                  onClick={() => store.setOuts(n)}
                  className={cn('btn-chip w-9', store.outs === n && 'is-active')}
                >
                  {n}
                </button>
              ))}
            </div>
          </label>
        </div>

        <div className="mt-2">
          <span className="text-xs" style={{ color: 'var(--muted)' }}>Runners</span>
          <div className="flex gap-2 mt-1">
            {(['on_1b', 'on_2b', 'on_3b'] as const).map((base) => (
              <button
                key={base}
                onClick={() => store.setRunners({ [base]: !store.runners[base] })}
                className={cn('btn-chip w-11', store.runners[base] && 'is-active')}
              >
                {base === 'on_1b' ? '1B' : base === 'on_2b' ? '2B' : '3B'}
              </button>
            ))}
          </div>
        </div>

        <label className="text-xs mt-2 block" style={{ color: 'var(--muted)' }}>
          Score diff (us − them)
          <input
            type="number"
            value={store.scoreDiff}
            onChange={(e) => store.setScoreDiff(Number(e.target.value))}
            className="block w-20 mt-0.5"
            min={-20}
            max={20}
          />
        </label>
      </Section>

      <Section title="Optimize For">
        <div className="flex flex-col gap-1">
          {(['balanced', 'prevent_hit', 'prevent_extra_base'] as const).map((opt) => (
            <button
              key={opt}
              onClick={() => store.setOptimizeFor(opt)}
              className={cn('btn-chip text-left', store.optimizeFor === opt && 'is-active')}
            >
              {opt.replace(/_/g, ' ')}
            </button>
          ))}
        </div>
      </Section>

      <div className="mt-auto space-y-1.5">
        {!canRequest && (
          <p className="text-[11px] text-center" style={{ color: 'var(--muted)' }}>
            Select{' '}
            {[
              !store.batterId && 'a batter',
              !store.pitcherId && 'a pitcher',
              !store.teamId && 'a fielding team',
              !store.stadiumId && 'a ballpark',
            ]
              .filter(Boolean)
              .join(', ')}{' '}
            to continue
          </p>
        )}
        <button onClick={onRequestAlignment} disabled={!canRequest} className="btn-primary w-full">
          Get Alignment
        </button>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h3 className="panel-kicker">{title}</h3>
      {children}
    </div>
  )
}
