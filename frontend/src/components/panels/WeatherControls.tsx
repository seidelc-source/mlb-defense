import { useQuery } from '@tanstack/react-query'
import { useScenarioStore } from '@/stores/scenarioStore'
import { weatherApi } from '@/api/alignmentApi'
import { IS_DEMO } from '@/lib/demo'
import { useDemoManifest } from '@/demo/useDemoManifest'
import { cn } from '@/lib/cn'
import type { GameWeather } from '@/types'

// Baseball-intuitive wind directions → meteorological "from" degrees that the
// engine's wind decomposition expects (deg 180 = blowing out to CF).
const WIND_DIRS = [
  { label: 'Out to CF', deg: 180 },
  { label: 'Out to LF', deg: 135 },
  { label: 'Out to RF', deg: 225 },
  { label: 'In from CF', deg: 0 },
  { label: 'L → R (cross)', deg: 270 },
  { label: 'R → L (cross)', deg: 90 },
]

const LABEL_DEG: Record<string, number> = {
  N: 0, NE: 45, E: 90, SE: 135, S: 180, SW: 225, W: 270, NW: 315,
}

export function snapDir(deg: number): number {
  let best = WIND_DIRS[0].deg
  let bestDist = 360
  for (const o of WIND_DIRS) {
    const raw = Math.abs(o.deg - deg)
    const dist = Math.min(raw, 360 - raw)
    if (dist < bestDist) {
      bestDist = dist
      best = o.deg
    }
  }
  return best
}

export function WeatherControls({
  stadiumId,
  liveWeather,
}: {
  stadiumId: string | null
  liveWeather: GameWeather | null
}) {
  const weather = useScenarioStore((s) => s.weather)
  const setWeather = useScenarioStore((s) => s.setWeather)

  const { data: effect } = useQuery({
    queryKey: [
      'weather-preview', stadiumId,
      weather.temperature_f, weather.wind_speed_mph,
      weather.wind_direction_deg, weather.humidity_pct,
    ],
    queryFn: () =>
      weatherApi.preview(
        {
          temperature_f: weather.temperature_f,
          humidity_pct: weather.humidity_pct,
          wind_speed_mph: weather.wind_speed_mph,
          wind_direction_deg: weather.wind_direction_deg,
        },
        stadiumId ?? undefined,
      ),
    enabled: weather.enabled,
    staleTime: 60_000,
  })

  const useLive = () => {
    if (!liveWeather) return
    const labelDeg = liveWeather.wind_direction_label
      ? LABEL_DEG[liveWeather.wind_direction_label]
      : undefined
    setWeather({
      enabled: true,
      temperature_f:
        liveWeather.temperature_f != null
          ? Math.round(liveWeather.temperature_f)
          : weather.temperature_f,
      wind_speed_mph:
        liveWeather.wind_speed_mph != null
          ? Math.round(liveWeather.wind_speed_mph)
          : weather.wind_speed_mph,
      humidity_pct:
        liveWeather.humidity_pct != null
          ? Math.round(liveWeather.humidity_pct)
          : weather.humidity_pct,
      wind_direction_deg: labelDeg != null ? snapDir(labelDeg) : weather.wind_direction_deg,
    })
  }

  return (
    <div className="panel">
      <div className="flex items-center justify-between mb-2">
        <h3 className="panel-kicker">Weather</h3>
        {!IS_DEMO && (
          <label className="flex items-center gap-1.5 text-xs cursor-pointer" style={{ color: 'var(--muted)' }}>
            <input
              type="checkbox"
              checked={weather.enabled}
              onChange={(e) => setWeather({ enabled: e.target.checked })}
            />
            Manual
          </label>
        )}
      </div>

      {liveWeather && (
        <div className="flex items-center justify-between mb-2 text-xs" style={{ color: 'var(--muted)' }}>
          <span>
            Live:{' '}
            {liveWeather.temperature_f != null ? `${Math.round(liveWeather.temperature_f)}°F` : '—'}
            {liveWeather.wind_speed_mph != null
              ? `, ${Math.round(liveWeather.wind_speed_mph)} mph ${liveWeather.wind_direction_label ?? ''}`
              : ''}
          </span>
          <button onClick={useLive} className="btn-chip !min-h-[22px] !px-2 text-[11px]">
            Use live
          </button>
        </div>
      )}

      {IS_DEMO ? (
        <DemoPresets effectSummary={weather.enabled && effect ? effect : null} />
      ) : weather.enabled ? (
        <div className="space-y-2">
          <Slider
            label={`Temp ${weather.temperature_f}°F`}
            min={20} max={110} value={weather.temperature_f}
            onChange={(v) => setWeather({ temperature_f: v })}
          />
          <Slider
            label={`Wind ${weather.wind_speed_mph} mph`}
            min={0} max={40} value={weather.wind_speed_mph}
            onChange={(v) => setWeather({ wind_speed_mph: v })}
          />
          <label className="block text-xs" style={{ color: 'var(--muted)' }}>
            Direction
            <select
              value={weather.wind_direction_deg}
              onChange={(e) => setWeather({ wind_direction_deg: Number(e.target.value) })}
              className="block w-full mt-0.5"
            >
              {WIND_DIRS.map((o) => (
                <option key={o.deg} value={o.deg}>{o.label}</option>
              ))}
            </select>
          </label>
          <Slider
            label={`Humidity ${weather.humidity_pct}%`}
            min={0} max={100} value={weather.humidity_pct}
            onChange={(v) => setWeather({ humidity_pct: v })}
          />

          {effect && (
            <div
              className="text-xs rounded-md px-2 py-1.5 mt-1"
              style={{ border: '1px solid var(--line)' }}
            >
              <span
                className="font-extrabold"
                style={{ color: effect.carry_pct >= 0 ? 'var(--ok)' : 'var(--danger)' }}
              >
                {effect.carry_pct >= 0 ? '+' : ''}{effect.carry_pct}% carry
              </span>
              <span style={{ color: 'var(--muted)' }}> · {effect.summary}</span>
            </div>
          )}
          <p className="text-[10px]" style={{ color: 'var(--muted)' }}>
            Applied to the next recommendation.
          </p>
        </div>
      ) : (
        <p className="text-xs" style={{ color: 'var(--muted)' }}>
          Toggle <b>Manual</b> to set conditions and factor weather into the recommendation.
        </p>
      )}
    </div>
  )
}

// Demo builds precompute weather effects for a fixed preset list, so the
// continuous sliders are replaced by preset chips.
function DemoPresets({ effectSummary }: { effectSummary: import('@/types').WeatherEffect | null }) {
  const weather = useScenarioStore((s) => s.weather)
  const setWeather = useScenarioStore((s) => s.setWeather)
  const { data: manifest } = useDemoManifest()

  const activeId = !weather.enabled
    ? 'off'
    : manifest?.weather_presets.find(
        (p) =>
          p.input &&
          p.input.temperature_f === weather.temperature_f &&
          p.input.humidity_pct === weather.humidity_pct &&
          p.input.wind_speed_mph === weather.wind_speed_mph &&
          p.input.wind_direction_deg === weather.wind_direction_deg
      )?.id

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1">
        {(manifest?.weather_presets ?? []).map((p) => (
          <button
            key={p.id}
            onClick={() =>
              p.input
                ? setWeather({ enabled: true, ...p.input })
                : setWeather({ enabled: false })
            }
            className={cn('btn-chip text-[11px]', activeId === p.id && 'is-active')}
          >
            {p.label}
          </button>
        ))}
      </div>
      {effectSummary && (
        <div className="text-xs rounded-md px-2 py-1.5" style={{ border: '1px solid var(--line)' }}>
          <span
            className="font-extrabold"
            style={{ color: effectSummary.carry_pct >= 0 ? 'var(--ok)' : 'var(--danger)' }}
          >
            {effectSummary.carry_pct >= 0 ? '+' : ''}{effectSummary.carry_pct}% carry
          </span>
          <span style={{ color: 'var(--muted)' }}> · {effectSummary.summary}</span>
        </div>
      )}
      <p className="text-[10px]" style={{ color: 'var(--muted)' }}>
        Applied to the next recommendation.
      </p>
    </div>
  )
}

function Slider({
  label, min, max, value, onChange,
}: {
  label: string
  min: number
  max: number
  value: number
  onChange: (v: number) => void
}) {
  return (
    <label className="block text-xs" style={{ color: 'var(--muted)' }}>
      {label}
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="block w-full mt-0.5"
      />
    </label>
  )
}
