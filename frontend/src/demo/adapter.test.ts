// Exercises the demo adapter against the REAL generated fixtures in
// public/demo-data (fetch is stubbed to read from disk), so route matching and
// fixture naming can't drift from what build_demo_fixtures.py writes.
// Skips when fixtures haven't been generated locally.
import { beforeAll, afterAll, describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'fs'
import path from 'path'
import type { InternalAxiosRequestConfig } from 'axios'
import { demoAdapter, loadDemoManifest } from './adapter'
import type { DemoManifest } from '@/lib/demo'

const DATA_DIR = path.resolve(__dirname, '../../public/demo-data')
const hasFixtures = existsSync(path.join(DATA_DIR, 'manifest.json'))

const realFetch = globalThis.fetch

function cfg(partial: Partial<InternalAxiosRequestConfig>): InternalAxiosRequestConfig {
  return { headers: {}, ...partial } as InternalAxiosRequestConfig
}

describe.skipIf(!hasFixtures)('demo adapter ↔ generated fixtures', () => {
  let manifest: DemoManifest

  beforeAll(async () => {
    globalThis.fetch = (async (url: string | URL) => {
      const rel = String(url).replace(/^\/demo-data\//, '')
      const file = path.join(DATA_DIR, rel)
      if (!existsSync(file)) return { ok: false, status: 404 } as Response
      return { ok: true, json: async () => JSON.parse(readFileSync(file, 'utf-8')) } as Response
    }) as typeof fetch
    manifest = await loadDemoManifest()
  })

  afterAll(() => {
    globalThis.fetch = realFetch
  })

  it('serves teams and stadiums', async () => {
    const teams = await demoAdapter(cfg({ method: 'get', url: '/teams' }))
    expect(teams.data.length).toBe(30)
    const stadiums = await demoAdapter(cfg({ method: 'get', url: '/stadiums' }))
    expect(stadiums.data.length).toBeGreaterThan(0)
  })

  it('serves every matchup fixture the manifest advertises', async () => {
    expect(manifest.matchups.length).toBeGreaterThan(0)
    for (const m of manifest.matchups) {
      for (const preset of manifest.weather_presets) {
        const res = await demoAdapter(
          cfg({
            method: 'post',
            url: '/alignments/recommend',
            data: JSON.stringify({
              team_id: m.team_id,
              batter_id: m.batter_id,
              pitcher_id: m.pitcher_id,
              stadium_id: m.stadium_id,
              optimize_for: 'balanced',
              ...(preset.input ? { weather: preset.input } : {}),
            }),
          })
        )
        expect(res.data.fielder_positions).toBeDefined()
        expect(res.data.calibrator_version).toBeTruthy()
      }
    }
  })

  it('serves layout, roster, weather preview, spray, and player pages per matchup', async () => {
    const m = manifest.matchups[0]
    const layout = await demoAdapter(cfg({ method: 'get', url: `/stadiums/${m.stadium_id}/layout` }))
    expect(layout.data.name).toBeTruthy()
    const roster = await demoAdapter(cfg({ method: 'get', url: `/teams/${m.team_id}/roster` }))
    expect(roster.data.length).toBeGreaterThan(0)
    const preset = manifest.weather_presets.find((p) => p.input)!
    const preview = await demoAdapter(
      cfg({
        method: 'post',
        url: '/weather/preview',
        data: JSON.stringify(preset.input),
        params: { stadium_id: m.stadium_id },
      })
    )
    expect(preview.data.carry_pct).toBeDefined()

    const seasons = await demoAdapter(cfg({ method: 'get', url: `/spray/${m.batter_id}/seasons` }))
    expect(seasons.data.length).toBeGreaterThan(0)
    const spray = await demoAdapter(
      cfg({ method: 'get', url: `/spray/${m.batter_id}`, params: { season: seasons.data[0] } })
    )
    expect(spray.data.zones.length).toBeGreaterThan(0)

    const detail = await demoAdapter(cfg({ method: 'get', url: `/players/${m.batter_id}` }))
    expect(detail.data.full_name).toBeTruthy()
    const fSeasons = await demoAdapter(
      cfg({ method: 'get', url: `/players/${m.batter_id}/fielding/seasons` })
    )
    const fielding = await demoAdapter(
      cfg({
        method: 'get',
        url: `/players/${m.batter_id}/fielding`,
        params: { season: fSeasons.data[0] ?? 2024 },
      })
    )
    expect(Array.isArray(fielding.data)).toBe(true)
  })

  it('records history and rejects live-only endpoints with friendly errors', async () => {
    const m = manifest.matchups[0]
    const history = await demoAdapter(
      cfg({ method: 'get', url: '/alignments', params: { batter_id: m.batter_id, limit: 8 } })
    )
    expect(history.data.length).toBeGreaterThan(0) // recorded by the recommend test above
    expect(history.data[0].fielder_positions).toBeDefined()

    await expect(
      demoAdapter(cfg({ method: 'post', url: '/alignments/score', data: '{}' }))
    ).rejects.toMatchObject({ response: { data: { detail: expect.stringContaining('live engine') } } })
    await expect(
      demoAdapter(
        cfg({
          method: 'post',
          url: '/alignments/recommend',
          data: JSON.stringify({ batter_id: 'nope', pitcher_id: 'nope', team_id: 'x', stadium_id: 'y' }),
        })
      )
    ).rejects.toMatchObject({ response: { data: { detail: expect.stringContaining('featured matchup') } } })
  })

  it('filters the featured player list like the backend would', async () => {
    const pitchers = await demoAdapter(
      cfg({ method: 'get', url: '/players', params: { role: 'pitcher' } })
    )
    expect(pitchers.data.players.length).toBeGreaterThan(0)
    expect(pitchers.data.players.every((p: { position: string }) => p.position === 'P')).toBe(true)
    const judge = await demoAdapter(
      cfg({ method: 'get', url: '/players', params: { name: 'judge', role: 'batter' } })
    )
    expect(judge.data.players.map((p: { full_name: string }) => p.full_name)).toContain('Aaron Judge')
  })
})
