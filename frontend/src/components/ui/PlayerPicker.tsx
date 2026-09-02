import { useState, useRef, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { playerApi, type PlayerSearchParams } from '@/api/playerApi'
import type { PlayerSummary } from '@/types'

interface Props {
  label: string
  value: string | null
  onSelect: (id: string) => void
  /** Scope the picker to one team's roster (with an All-MLB escape hatch). */
  teamId?: string | null
  /** Restrict by role: batters (non-pitchers) or pitchers. */
  role?: 'batter' | 'pitcher'
  placeholder?: string
  className?: string
}

export function PlayerPicker({
  label,
  value,
  onSelect,
  teamId = null,
  role,
  placeholder,
  className,
}: Props) {
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [allMlb, setAllMlb] = useState(false)
  const wrapperRef = useRef<HTMLDivElement>(null)

  const scopedToTeam = !!teamId && !allMlb

  // Roster mode: load the whole team-scoped list once, filter client-side
  const rosterQuery = useQuery({
    queryKey: ['picker-roster', teamId, role],
    queryFn: () =>
      playerApi.list({ team_id: teamId!, role, active: true, limit: 60 }),
    enabled: scopedToTeam,
    staleTime: 5 * 60_000,
  })

  // Global search mode (no team, or "All MLB" toggled)
  const searchParams: PlayerSearchParams = { name: search, role, limit: 8, active: true }
  const searchQuery = useQuery({
    queryKey: ['picker-search', searchParams],
    queryFn: () => playerApi.list(searchParams),
    enabled: !scopedToTeam && search.length >= 2,
    staleTime: 30_000,
  })

  const selectedPlayer = useQuery({
    queryKey: ['player-summary', value],
    queryFn: () => playerApi.get(value!),
    enabled: !!value,
    staleTime: 60_000,
  })

  const options: PlayerSummary[] = useMemo(() => {
    if (scopedToTeam) {
      const roster = rosterQuery.data?.players ?? []
      const sorted = [...roster].sort((a, b) => a.full_name.localeCompare(b.full_name))
      if (!search) return sorted
      const q = search.toLowerCase()
      return sorted.filter((p) => p.full_name.toLowerCase().includes(q))
    }
    return searchQuery.data?.players ?? []
  }, [scopedToTeam, rosterQuery.data, searchQuery.data, search])

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Switching teams invalidates the current scoping toggle
  useEffect(() => {
    setAllMlb(false)
  }, [teamId])

  const showDropdown = open && (options.length > 0 || scopedToTeam)

  return (
    <div ref={wrapperRef} className={`relative ${className ?? ''}`}>
      <label className="text-xs" style={{ color: 'var(--muted)' }}>{label}</label>
      <input
        type="text"
        value={open ? search : (selectedPlayer.data?.full_name ?? search)}
        onChange={(e) => {
          setSearch(e.target.value)
          setOpen(true)
        }}
        onFocus={() => {
          setSearch('')
          setOpen(true)
        }}
        placeholder={
          placeholder ??
          (scopedToTeam ? `Pick ${label.toLowerCase()}…` : `Search ${label.toLowerCase()}...`)
        }
        className="block w-full mt-0.5"
      />
      {showDropdown && (
        <div
          className="absolute z-20 w-full mt-1 rounded-md shadow-lg overflow-hidden"
          style={{ background: '#fff', border: '1px solid var(--line)' }}
        >
          <ul className="max-h-52 overflow-y-auto">
            {options.length === 0 && (
              <li className="px-3 py-2 text-xs" style={{ color: 'var(--muted)' }}>
                {scopedToTeam && rosterQuery.isLoading ? 'Loading roster…' : 'No matches'}
              </li>
            )}
            {options.map((p) => (
              <li key={p.id}>
                <button
                  onClick={() => {
                    onSelect(p.id)
                    setSearch(p.full_name)
                    setOpen(false)
                  }}
                  className="w-full text-left px-3 py-1.5 text-sm flex justify-between hover:brightness-95"
                  style={{ background: '#fff', color: 'var(--ink)' }}
                >
                  <span>{p.full_name}</span>
                  <span className="text-xs" style={{ color: 'var(--muted)' }}>
                    {p.position} · {p.bats}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {teamId && (
            <button
              onClick={() => setAllMlb((v) => !v)}
              className="w-full text-left px-3 py-1.5 text-[11px] font-bold uppercase"
              style={{
                background: '#edf1ea',
                color: allMlb ? 'var(--clay-dark)' : 'var(--muted)',
                borderTop: '1px solid var(--line)',
              }}
            >
              {allMlb ? '← Back to roster' : 'Search all MLB →'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
