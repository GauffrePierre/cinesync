import { Bookmark, CalendarDays, Compass, Library, Newspaper, Popcorn, User } from 'lucide-react'
import { useStatus } from '../../hooks/useMedia'

export const NAV_ITEMS = [
  { to: '/', label: 'Découvrir', icon: Compass, end: true },
  { to: '/upcoming', label: 'À venir', icon: CalendarDays },
  { to: '/news', label: 'Actu Ciné', short: 'Actu', icon: Newspaper },
  { to: '/library', label: 'Bibliothèque', icon: Library, needs: 'plex' }, // bibliothèque Plex
  { to: '/tonight', label: 'Pour ce soir', icon: Popcorn },
  { to: '/watchlist', label: 'Watchlist', icon: Bookmark },
  { to: '/profile', label: 'Profil', icon: User },
]

// Onglets visibles : ceux qui dépendent d'un service optionnel (Plex) n'apparaissent que s'il est relié
export function useNavItems() {
  const { data: status } = useStatus()
  return NAV_ITEMS.filter((i) => !i.needs || status?.[i.needs]?.configured)
}
