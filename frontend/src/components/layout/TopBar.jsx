import { Link } from 'react-router'
import { Search } from 'lucide-react'
import Logo from './Logo'
import NotificationBell from '../notifications/NotificationBell'
import { useUiStore } from '../../store/uiStore'
import { useT } from '../../i18n'

// Barre haute : logo (mobile) + loupe permanente + cloche
export default function TopBar() {
  const t = useT()
  const setSearchOpen = useUiStore((s) => s.setSearchOpen)
  return (
    <header className="pt-safe sticky top-0 z-30 border-b border-line bg-bg/80 backdrop-blur-xl lg:border-none lg:bg-transparent lg:backdrop-blur-none">
      <div className="flex h-14 items-center justify-between px-4 md:px-8 lg:h-16 lg:justify-end">
        <Link to="/" className="lg:hidden">
          <Logo />
        </Link>
        <div className="flex items-center gap-1 lg:gap-2">
          <button
            onClick={() => setSearchOpen(true)}
            className="hidden h-10 w-64 items-center gap-2 rounded-xl border border-line bg-bg2/80 px-3 text-sm text-text3 backdrop-blur-xl transition hover:text-text2 lg:flex"
          >
            <Search className="h-4 w-4" />
            {t('Rechercher…')}
            <kbd className="ml-auto rounded-md border border-line px-1.5 text-[10px]">/</kbd>
          </button>
          <button
            onClick={() => setSearchOpen(true)}
            className="rounded-full p-2 text-text2 hover:bg-bg3 hover:text-text lg:hidden"
            aria-label={t('Rechercher')}
          >
            <Search className="h-5 w-5" />
          </button>
          <NotificationBell />
        </div>
      </div>
    </header>
  )
}
