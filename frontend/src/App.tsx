import { BrowserRouter, HashRouter, Routes, Route, NavLink } from 'react-router-dom'
import { FieldView } from '@/pages/FieldView'
import { SprayAnalysis } from '@/pages/SprayAnalysis'
import { PlayerProfile } from '@/pages/PlayerProfile'
import { IngestDashboard } from '@/pages/IngestDashboard'
import { IS_DEMO } from '@/lib/demo'

const navItems = [
  { to: '/', label: 'Field View' },
  { to: '/spray', label: 'Spray Analysis' },
  { to: '/players', label: 'Players' },
  // Ingest triggers a live pipeline — meaningless without a backend
  ...(IS_DEMO ? [] : [{ to: '/ingest', label: 'Ingest' }]),
]

// GitHub Pages serves a single static entry point, so demo builds use
// hash-based routing to keep deep links refreshable.
const Router = IS_DEMO ? HashRouter : BrowserRouter

export default function App() {
  return (
    <Router>
      <div className="flex flex-col h-screen">
        <nav
          className="flex items-center gap-1 px-4 py-2 shrink-0 border-b"
          style={{ background: 'rgba(255,255,255,0.92)', borderColor: 'var(--line)' }}
        >
          <span
            className="font-extrabold text-sm tracking-wide mr-4"
            style={{ color: 'var(--field-deep)' }}
          >
            ⬥ MLB Defense
          </span>
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className="px-3 py-1.5 text-sm font-semibold rounded-md transition-colors"
              style={({ isActive }) =>
                isActive
                  ? { background: '#f2dfc9', color: 'var(--clay-dark)', border: '1px solid var(--clay)' }
                  : { color: 'var(--muted)', border: '1px solid transparent' }
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        {IS_DEMO && (
          <div
            className="px-4 py-1.5 text-xs shrink-0 border-b"
            style={{ background: '#f7ecd9', color: '#8a6116', borderColor: 'var(--line)' }}
          >
            <b>Static demo</b> — precomputed featured scenarios; fielder-drag re-scoring,
            arbitrary matchups, and data ingest need the live engine.{' '}
            <a
              href="https://github.com/seidelc-source/mlb-defense"
              target="_blank"
              rel="noreferrer"
              className="underline font-semibold"
            >
              Run it locally →
            </a>
          </div>
        )}

        <main className="flex-1 overflow-hidden">
          <Routes>
            <Route path="/" element={<FieldView />} />
            <Route path="/spray" element={<SprayAnalysis />} />
            <Route path="/players" element={<PlayerProfile />} />
            {!IS_DEMO && <Route path="/ingest" element={<IngestDashboard />} />}
          </Routes>
        </main>
      </div>
    </Router>
  )
}
