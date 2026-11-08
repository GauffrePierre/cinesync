import { BarChart3, Bookmark, CalendarDays, Compass, Inbox, Layers, Library, Newspaper, Popcorn, ShieldCheck, User } from 'lucide-react'
import { useLocation } from 'react-router'
import { useSettings, useStatus } from '../../hooks/useMedia'
import { useIsAdmin } from '../../hooks/useAuth'

export const NAV_ITEMS = [
  { key: 'discover', to: '/', label: 'Découvrir', icon: Compass, end: true },
  { key: 'upcoming', to: '/upcoming', label: 'À venir', icon: CalendarDays },
  { key: 'news', to: '/news', label: 'Actu Ciné', short: 'Actu', icon: Newspaper },
  { key: 'library', to: '/library', label: 'Bibliothèque', icon: Library, needs: 'plex' }, // bibliothèque Plex
  { key: 'tonight', to: '/tonight', label: 'Pour ce soir', icon: Popcorn },
  { key: 'watchlist', to: '/watchlist', label: 'Watchlist', icon: Bookmark },
  { key: 'profile', to: '/profile', label: 'Profil', icon: User },
]

// Menu de la version ordinateur : onglets principaux puis outils (ordre réglable dans le Profil)
export const SIDEBAR_ITEMS = [
  ...NAV_ITEMS,
  { key: 'swipe', to: '/swipe', label: 'Mode swipe', icon: Layers },
  { key: 'stats', to: '/stats', label: 'Statistiques', icon: BarChart3 },
  { key: 'requests', to: '/admin?tab=requests', label: 'Demandes', icon: Inbox, admin: true, needs: 'plex' }, // file des demandes
  { key: 'admin', to: '/admin', label: 'Espace admin', icon: ShieldCheck, admin: true },
]

// Onglets visibles : ceux qui dépendent d'un service optionnel (Plex) n'apparaissent que s'il est relié
export function useNavItems() {
  const { data: status } = useStatus()
  return NAV_ITEMS.filter((i) => !i.needs || status?.[i.needs]?.configured)
}

/** Ordre choisi (clés inconnues ignorées, nouveaux onglets ajoutés à la fin dans l'ordre par défaut). */
export function orderItems(items, order = []) {
  const byKey = new Map(items.map((i) => [i.key, i]))
  const ordered = order.map((k) => byKey.get(k)).filter(Boolean)
  return [...ordered, ...items.filter((i) => !order.includes(i.key))]
}

/** Onglets du menu ordinateur visibles pour ce compte, dans son ordre. */
export function useSidebarItems() {
  const { data: status } = useStatus()
  const { data: settings } = useSettings()
  const isAdmin = useIsAdmin()
  const visible = SIDEBAR_ITEMS.filter((i) => (!i.admin || isAdmin) && (!i.needs || status?.[i.needs]?.configured))
  return orderItems(visible, settings?.nav_order || [])
}

/** Onglet actif, en tenant compte de l'onglet de l'espace admin (Demandes = /admin?tab=requests). */
export function useIsActive() {
  const { pathname, search } = useLocation()
  const tab = new URLSearchParams(search).get('tab')
  return (item) => {
    if (item.key === 'requests') return pathname === '/admin' && tab === 'requests'
    if (item.key === 'admin') return pathname === '/admin' && tab !== 'requests'
    return item.end ? pathname === item.to : pathname === item.to || pathname.startsWith(`${item.to}/`)
  }
}
