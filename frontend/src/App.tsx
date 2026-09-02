import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { FieldView } from '@/pages/FieldView'
import { SprayAnalysis } from '@/pages/SprayAnalysis'
import { PlayerProfile } from '@/pages/PlayerProfile'
import { IngestDashboard } from '@/pages/IngestDashboard'

const navItems = [
  { to: '/', label: 'Field View' },
  { to: '/spray', label: 'Spray Analysis' },
  { to: '/players', label: 'Players' },
  { to: '/ingest', label: 'Ingest' },
]

export default function App() {
  return (
    <BrowserRouter>
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

        <main className="flex-1 overflow-hidden">
          <Routes>
            <Route path="/" element={<FieldView />} />
            <Route path="/spray" element={<SprayAnalysis />} />
            <Route path="/players" element={<PlayerProfile />} />
            <Route path="/ingest" element={<IngestDashboard />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
