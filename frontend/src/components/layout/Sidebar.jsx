import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import Logo from './Logo'
import { useIsActive, useSidebarItems } from './nav'
import { useSettings, useStatus } from '../../hooks/useMedia'
import { useIsAdmin } from '../../hooks/useAuth'
import { requests } from '../../services/requests'
import { api } from '../../services/api'
import { useT } from '../../i18n'

const SERVICES = {
  tmdb: { label: 'TMDB', color: '#01b4e4' },
  plex: { label: 'Plex', color: 'var(--plex)' },
  jellyfin: { label: 'Jellyfin', color: '#aa5cc3' },
  trakt: { label: 'Trakt', color: 'var(--trakt)' },
  seerr: { label: 'Seerr', color: 'var(--seerr)' },
  justwatch: { label: 'JustWatch', color: 'var(--justwatch)' },
  letterboxd: { label: 'Letterboxd', color: 'var(--letterboxd)' },
  cinema: { label: 'Cinéma', color: '#f59e0b' },
}

// Pastille d'un service utilisé : même code pour tous — vert s'il répond, gris pendant la vérification,
// rouge clignotant s'il est en panne
function ServiceDot({ id, health }) {
  const t = useT()
  const s = SERVICES[id]
  const down = health && !health.ok
  const title = health ? t(health.message) : t('Vérification en cours…')
  return (
    <li>
      <Link to="/profile?tab=connections" title={title} className={`flex items-center gap-2.5 rounded-lg px-3 py-1 text-xs hover:text-text ${down ? 'text-red-400' : 'text-text2'}`}>
        <span className="relative flex h-2 w-2">
          {down && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75" />}
          <span
            className={`relative inline-flex h-2 w-2 rounded-full ${
              down ? 'animate-pulse bg-red-500' : health ? 'bg-emerald-500 shadow-[0_0_8px_rgb(16_185_129)]' : 'bg-text3'
            }`}
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
  const items = useSidebarItems()
  const isActive = useIsActive()
  const { data: settings } = useSettings()
  const custom = (settings?.nav_order || []).length > 0
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: () => api.get('/health'), staleTime: Infinity })
  const isAdmin = useIsAdmin()
  const { data: queue } = useQuery({ queryKey: ['requests', 'all'], queryFn: () => requests.list('all'), enabled: isAdmin, staleTime: 60_000 })
  const pending = queue?.pending || 0

  return (
    <aside className="no-scrollbar fixed inset-y-0 left-0 z-40 hidden w-[200px] flex-col overflow-y-auto border-r border-line bg-bg2/60 px-3 py-5 backdrop-blur-xl lg:flex">
      <Link to="/" className="mb-8 px-2">
        <Logo />
      </Link>

      <nav className="flex flex-col gap-0.5">
        {items.map((item, n) => {
          const Icon = item.icon
          const active = isActive(item)
          // Petit espace avant les outils, tant que l'ordre par défaut est gardé
          const gap = !custom && item.key === 'swipe' && n > 0
          const badge = item.key === (items.some((i) => i.key === 'requests') ? 'requests' : 'admin') && pending > 0
          return (
            <Link
              key={item.key}
              to={item.to}
              className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition ${gap ? 'mt-2' : ''} ${
                active ? 'bg-accent/15 text-accent2' : 'text-text2 hover:bg-bg3 hover:text-text'
              }`}
              aria-current={active ? 'page' : undefined}
            >
              <Icon className="h-[18px] w-[18px] shrink-0" />
              <span className="whitespace-nowrap">{t(item.label)}</span>
              {badge && (
                <span className="ml-auto rounded-full bg-accent px-1.5 text-[10px] font-semibold text-white" title={t('{n} demandes en attente', { n: pending })}>
                  {pending}
                </span>
              )}
            </Link>
          )
        })}
      </nav>

      <div className="mt-auto pt-6">
        {/* Version sur la ligne du titre « Services » : toujours visible, même avec beaucoup de services */}
        <div className="mb-2 flex items-baseline justify-between gap-2 px-3">
          {used.length > 0 && <p className="text-xs font-medium text-text3">{t('Services')}</p>}
          {health?.version && (
            <Link to="/profile" className="ml-auto text-[11px] tabular-nums text-text3 hover:text-text2" title={t('À propos')}>
              v{health.version}
            </Link>
          )}
        </div>
        {used.length > 0 && (
          <ul className="flex flex-col gap-1">
            {used.map((id) => (
              <ServiceDot key={id} id={id} health={status.health[id]} />
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}
