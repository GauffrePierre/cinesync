import { Suspense, useEffect } from 'react'
import { Outlet, useLocation } from 'react-router'
import Sidebar from './Sidebar'
import BottomBar from './BottomBar'
import TopBar from './TopBar'
import SearchOverlay from '../search/SearchOverlay'
import Toaster from '../ui/Toaster'
import AppChooser from '../ui/AppChooser'
import Skeleton from '../ui/Skeleton'
import { useUiStore } from '../../store/uiStore'

export default function AppLayout() {
  const { pathname } = useLocation()
  const setSearchOpen = useUiStore((s) => s.setSearchOpen)

  // Remonte en haut à chaque changement de page
  // Bloc explicite : dans les navigateurs récents, scrollTo() renvoie une Promise,
  // que React prendrait pour une fonction de nettoyage (et planterait)
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  // Raccourcis : « / » ou Ctrl/Cmd+K ouvrent la recherche
  useEffect(() => {
    const onKey = (e) => {
      const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) {
        e.preventDefault()
        setSearchOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setSearchOpen])

  return (
    <div className="min-h-dvh bg-bg text-text">
      <Sidebar />
      <div className="lg:pl-[200px]">
        <TopBar />
        <main className="px-4 pb-28 pt-4 md:px-8 md:pt-6 lg:pb-12">
          {/* Page en cours de chargement : le menu reste en place */}
          <Suspense fallback={<Skeleton className="h-64 rounded-2xl" />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
      <BottomBar />
      <SearchOverlay />
      <Toaster />
      <AppChooser />
    </div>
  )
}
