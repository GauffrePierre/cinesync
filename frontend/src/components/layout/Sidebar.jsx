import { Link, NavLink } from 'react-router'
import { BarChart3, Layers, ShieldCheck } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import Logo from './Logo'
import { useNavItems } from './nav'
import { useStatus } from '../../hooks/useMedia'
import { useIsAdmin } from '../../hooks/useAuth'
import { requests } from '../../services/requests'
import { api } from '../../services/api'
import { useT } from '../../i18n'

const SERVICES = {
  tmdb: { label: 'TMDB', color: '#01b4e4' },
  plex: { label: 'Plex', color: 'var(--plex)' },
  trakt: { label: 'Trakt', color: 'var(--trakt)' },
  seerr: { label: 'Seerr', color: 'var(--seerr)' },
  justwatch: { label: 'JustWatch', color: 'var(--justwatch)' },
  letterboxd: { label: 'Letterboxd', color: 'var(--letterboxd)' },
  cinema: { label: 'Cinéma', color: '#f59e0b' },
}

// Pastille d'un service utilisé : couleur du service si OK, rouge clignotant si en panne
function ServiceDot({ id, health }) {
  const t = useT()
  const s = SERVICES[id]
  const down = health && !health.ok
  const title = health ? t(health.message) : t('Vérification en cours…')
  return (
    <li>
      <Link to="/profile" title={title} className={`flex items-center gap-2.5 rounded-lg px-3 py-1 text-xs hover:text-text ${down ? 'text-red-400' : 'text-text2'}`}>
        <span className="relative flex h-2 w-2">
          {down && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75" />}
          <span
            className={`relative inline-flex h-2 w-2 rounded-full ${down ? 'animate-pulse bg-red-500' : ''}`}
            style={down ? undefined : { background: s.color, boxShadow: `0 0 8px ${s.color}`, opacity: health ? 1 : 0.5 }}
          />
        </span>
        <span className={down ? 'animate-pulse font-medium' : ''}>{t(s.label)}</span>
      </Link>
    </li>
  )
}

// Navigation desktop : sidebar fixe 200px avec les services utilisés
export default function Sidebar() {
  const t = useT()
  const { data: status } = useStatus()
  const used = Object.keys(status?.health || {}).filter((k) => SERVICES[k])
  const navItems = useNavItems()
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: () => api.get('/health'), staleTime: Infinity })
  const isAdmin = useIsAdmin()
  const { data: queue } = useQuery({ queryKey: ['requests', 'all'], queryFn: () => requests.list('all'), enabled: isAdmin, staleTime: 60_000 })
  const pending = queue?.pending || 0

  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-[200px] flex-col border-r border-line bg-bg2/60 px-3 py-5 backdrop-blur-xl md:flex">
      <Link to="/" className="mb-8 px-2">
        <Logo />
      </Link>

      <nav className="flex flex-col gap-0.5">
        {navItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition ${
                isActive ? 'bg-accent/15 text-accent2' : 'text-text2 hover:bg-bg3 hover:text-text'
              }`
            }
          >
            <Icon className="h-[18px] w-[18px]" />
            {t(label)}
          </NavLink>
        ))}
        <NavLink
          to="/swipe"
          className="mt-2 flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium text-text2 transition hover:bg-bg3 hover:text-text"
        >
          <Layers className="h-[18px] w-[18px]" />
          {t('Mode swipe')}
        </NavLink>
        <NavLink
          to="/stats"
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition ${isActive ? 'bg-accent/15 text-accent2' : 'text-text2 hover:bg-bg3 hover:text-text'}`
          }
        >
          <BarChart3 className="h-[18px] w-[18px]" />
          {t('Statistiques')}
        </NavLink>
        {isAdmin && (
          <NavLink
            to="/admin"
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition ${isActive ? 'bg-accent/15 text-accent2' : 'text-text2 hover:bg-bg3 hover:text-text'}`
            }
          >
            <ShieldCheck className="h-[18px] w-[18px] shrink-0" />
            <span className="whitespace-nowrap">{t('Espace admin')}</span>
            {pending > 0 && (
              <span className="ml-auto rounded-full bg-accent px-1.5 text-[10px] font-semibold text-white" title={t('{n} demandes en attente', { n: pending })}>
                {pending}
              </span>
            )}
          </NavLink>
        )}
      </nav>

      <div className="mt-auto">
        {used.length > 0 && (
          <>
            <p className="mb-2 px-3 text-xs font-medium text-text3">{t('Services')}</p>
            <ul className="flex flex-col gap-1">
              {used.map((id) => (
                <ServiceDot key={id} id={id} health={status.health[id]} />
              ))}
            </ul>
          </>
        )}
        {health?.version && (
          <Link to="/profile" className="mt-4 block px-3 text-[11px] text-text3 hover:text-text2" title={t('À propos')}>
            CinéSync {health.version}
          </Link>
        )}
      </div>
    </aside>
  )
}
