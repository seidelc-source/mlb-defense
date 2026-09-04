// Axios adapter for static demo mode: resolves every API call from prebaked
// JSON fixtures under `${BASE_URL}demo-data/` instead of a live backend.
// Fixture layout is produced by backend/scripts/build_demo_fixtures.py.
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import type { AlignmentHistoryItem, AlignmentResponse, PlayerSummary } from '@/types'
import type { DemoManifest } from '@/lib/demo'

const DATA_ROOT = `${import.meta.env.BASE_URL}demo-data`

const jsonCache = new Map<string, Promise<unknown>>()

function fetchFixture<T>(relPath: string): Promise<T> {
  let p = jsonCache.get(relPath)
  if (!p) {
    p = fetch(`${DATA_ROOT}/${relPath}`).then((r) => {
      if (!r.ok) throw demoError(`Fixture not found: ${relPath}`, 404)
      return r.json()
    })
    jsonCache.set(relPath, p)
  }
  return p as Promise<T>
}

export function loadDemoManifest(): Promise<DemoManifest> {
  return fetchFixture<DemoManifest>('manifest.json')
}

/** Error the apiClient interceptor unwraps via err.response.data.detail. */
function demoError(detail: string, status = 400) {
  return Object.assign(new Error(detail), {
    response: { status, data: { detail } },
  })
}

function ok(config: InternalAxiosRequestConfig, data: unknown): AxiosResponse {
  return { data, status: 200, statusText: 'OK', headers: {}, config }
}

// Recommendations viewed this session, newest first, for the history panel.
const sessionHistory: AlignmentHistoryItem[] = []

function recordHistory(res: AlignmentResponse, batterId: string, pitcherId: string) {
  const positions: Record<string, [number, number]> = {}
  for (const [pos, fp] of Object.entries(res.fielder_positions)) {
    positions[pos] = [fp.x, fp.y]
  }
  sessionHistory.unshift({
    id: res.alignment_id,
    shift_type: res.shift_type,
    batter_id: batterId,
    pitcher_id: pitcherId,
    inning: null,
    outs: null,
    fielder_positions: positions,
    predicted_oaa_delta: res.predicted_oaa_delta,
    predicted_hit_pct: res.predicted_hit_pct,
    confidence: res.confidence,
    optimize_for: res.optimize_for,
    created_at: new Date().toISOString(),
  })
}

function matchWeatherPreset(
  manifest: DemoManifest,
  weather: { temperature_f: number; humidity_pct: number; wind_speed_mph: number; wind_direction_deg: number } | undefined
): string | null {
  if (!weather) return 'off'
  for (const preset of manifest.weather_presets) {
    const w = preset.input
    if (
      w &&
      w.temperature_f === weather.temperature_f &&
      w.humidity_pct === weather.humidity_pct &&
      w.wind_speed_mph === weather.wind_speed_mph &&
      w.wind_direction_deg === weather.wind_direction_deg
    ) {
      return preset.id
    }
  }
  return null
}

async function recommend(config: InternalAxiosRequestConfig): Promise<AxiosResponse> {
  const req = typeof config.data === 'string' ? JSON.parse(config.data) : config.data
  const manifest = await loadDemoManifest()
  const matchup = manifest.matchups.find(
    (m) =>
      m.batter_id === req.batter_id &&
      m.pitcher_id === req.pitcher_id &&
      m.team_id === req.team_id &&
      m.stadium_id === req.stadium_id
  )
  if (!matchup) {
    throw demoError(
      'This combination is not precomputed. Pick a featured matchup — arbitrary scenarios need the live engine (run the app locally).'
    )
  }
  const presetId = matchWeatherPreset(manifest, req.weather)
  if (!presetId) {
    throw demoError('Custom weather is not precomputed — choose one of the demo weather presets.')
  }
  const optimizeFor = req.optimize_for ?? 'balanced'
  const res = await fetchFixture<AlignmentResponse>(
    `alignments/${matchup.id}__${presetId}__${optimizeFor}.json`
  )
  recordHistory(res, req.batter_id, req.pitcher_id)
  return ok(config, res)
}

async function listPlayers(config: InternalAxiosRequestConfig): Promise<AxiosResponse> {
  const p = (config.params ?? {}) as {
    name?: string
    team_id?: string
    role?: string
    limit?: number
  }
  const manifest = await loadDemoManifest()
  let players: PlayerSummary[] = manifest.players
  if (p.role === 'pitcher') players = players.filter((x) => x.position === 'P')
  if (p.role === 'batter') players = players.filter((x) => x.position !== 'P')
  if (p.team_id) players = players.filter((x) => x.team_id === p.team_id)
  if (p.name) {
    const q = p.name.toLowerCase()
    players = players.filter((x) => x.full_name.toLowerCase().includes(q))
  }
  if (p.limit) players = players.slice(0, p.limit)
  return ok(config, { total: players.length, players })
}

/** Route table: [method, regexp on the /api/v1-relative path, handler]. */
type Handler = (
  config: InternalAxiosRequestConfig,
  m: RegExpMatchArray
) => Promise<AxiosResponse> | AxiosResponse

const routes: Array<[string, RegExp, Handler]> = [
  ['get', /^\/teams$/, (c) => fetchFixture('teams.json').then((d) => ok(c, d))],
  ['get', /^\/teams\/([^/]+)\/roster$/, (c, m) => fetchFixture(`rosters/${m[1]}.json`).then((d) => ok(c, d))],
  ['get', /^\/stadiums$/, (c) => fetchFixture('stadiums.json').then((d) => ok(c, d))],
  ['get', /^\/stadiums\/([^/]+)\/layout$/, (c, m) => fetchFixture(`layouts/${m[1]}.json`).then((d) => ok(c, d))],

  ['get', /^\/weather\/current\/[^/]+$/, (c) => ok(c, null)],
  [
    'post',
    /^\/weather\/preview$/,
    async (c) => {
      const body = typeof c.data === 'string' ? JSON.parse(c.data) : c.data
      const manifest = await loadDemoManifest()
      const presetId = matchWeatherPreset(manifest, body)
      const stadiumId = (c.params as { stadium_id?: string } | undefined)?.stadium_id
      if (!presetId || presetId === 'off' || !stadiumId) {
        throw demoError('Weather preview is precomputed for the demo presets only.')
      }
      return ok(c, await fetchFixture(`weather/${stadiumId}__${presetId}.json`))
    },
  ],

  ['post', /^\/alignments\/recommend$/, (c) => recommend(c)],
  [
    'post',
    /^\/alignments\/score$/,
    () => {
      throw demoError('Custom-position scoring needs the live engine — run the app locally to drag fielders.')
    },
  ],
  [
    'get',
    /^\/alignments$/,
    (c) => {
      const batterId = (c.params as { batter_id?: string } | undefined)?.batter_id
      const items = batterId
        ? sessionHistory.filter((h) => h.batter_id === batterId)
        : sessionHistory
      const limit = (c.params as { limit?: number } | undefined)?.limit ?? 20
      return ok(c, items.slice(0, limit))
    },
  ],

  ['get', /^\/players$/, (c) => listPlayers(c)],
  ['get', /^\/players\/([^/]+)\/fielding\/seasons$/, (c, m) => fetchFixture(`players/${m[1]}/fielding_seasons.json`).then((d) => ok(c, d))],
  [
    'get',
    /^\/players\/([^/]+)\/fielding$/,
    (c, m) => {
      const season = (c.params as { season?: number } | undefined)?.season ?? 2024
      return fetchFixture(`players/${m[1]}/fielding_s${season}.json`).then((d) => ok(c, d))
    },
  ],
  ['get', /^\/players\/([^/]+)\/pitching\/seasons$/, (c, m) => fetchFixture(`players/${m[1]}/pitching_seasons.json`).then((d) => ok(c, d))],
  [
    'get',
    /^\/players\/([^/]+)\/pitching$/,
    (c, m) => {
      const season = (c.params as { season?: number } | undefined)?.season ?? 2024
      return fetchFixture(`players/${m[1]}/pitching_s${season}.json`).then((d) => ok(c, d))
    },
  ],
  ['get', /^\/players\/([^/]+)\/injury$/, (c) => ok(c, [])],
  [
    'post',
    /^\/players\/[^/]+\/injury$/,
    () => {
      throw demoError('Injury editing needs the live engine — run the app locally.')
    },
  ],
  [
    'put',
    /^\/players\/[^/]+\/injury\/[^/]+\/end$/,
    () => {
      throw demoError('Injury editing needs the live engine — run the app locally.')
    },
  ],
  ['get', /^\/players\/([^/]+)$/, (c, m) => fetchFixture(`players/${m[1]}/detail.json`).then((d) => ok(c, d))],
  ['get', /^\/range\/([^/]+)$/, (c, m) => fetchFixture(`players/${m[1]}/range.json`).then((d) => ok(c, d))],

  ['get', /^\/spray\/([^/]+)\/seasons$/, (c, m) => fetchFixture(`spray/${m[1]}/seasons.json`).then((d) => ok(c, d))],
  [
    'get',
    /^\/spray\/([^/]+)$/,
    (c, m) => {
      const p = (c.params ?? {}) as {
        season?: number
        pitch_type?: string
        pitcher_hand?: string
        speed_min?: number
      }
      if (p.pitch_type || p.speed_min !== undefined) {
        throw demoError('Pitch-type and speed filters are not precomputed in the demo.')
      }
      const season = p.season ?? 0
      const hand = p.pitcher_hand ?? 'all'
      return fetchFixture(`spray/${m[1]}/s${season}_h${hand}.json`).then((d) => ok(c, d))
    },
  ],
]

export const demoAdapter: AxiosAdapter = async (config) => {
  const method = (config.method ?? 'get').toLowerCase()
  // Path relative to the API root, query params live in config.params
  const path = (config.url ?? '').replace(/\?.*$/, '')
  for (const [m, re, handler] of routes) {
    if (m !== method) continue
    const match = path.match(re)
    if (match) return handler(config, match)
  }
  throw demoError(`Not available in the static demo: ${method.toUpperCase()} ${path}`, 404)
}
