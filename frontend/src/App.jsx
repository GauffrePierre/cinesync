import { Suspense, useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import AppLayout from './components/layout/AppLayout'
import Discover from './pages/Discover'
import lazyPage from './lib/lazyPage'
import { ForcePasswordChange, Login, Setup, Splash } from './pages/Login'
import { useMe } from './hooks/useAuth'
import { useSettings } from './hooks/useMedia'
import { useTheme } from './hooks/useTheme'
import { useSyncOnOpen } from './hooks/useSyncOnOpen'

// Pages chargées à la demande (Découvrir et la connexion restent dans le fichier principal)
const Upcoming = lazyPage(() => import('./pages/Upcoming'))
const Library = lazyPage(() => import('./pages/Library'))
const Watchlist = lazyPage(() => import('./pages/Watchlist'))
const Swipe = lazyPage(() => import('./pages/Swipe'))
const MediaDetail = lazyPage(() => import('./pages/MediaDetail'))
const Profile = lazyPage(() => import('./pages/Profile'))
const Stats = lazyPage(() => import('./pages/Stats'))
const Tonight = lazyPage(() => import('./pages/Tonight'))
const Admin = lazyPage(() => import('./pages/Admin'))
const News = lazyPage(() => import('./pages/News'))
const Onboarding = lazyPage(() => import('./pages/Onboarding'))

function AuthedApp() {
  useTheme()
  useSyncOnOpen() // synchro + actualisation à l'ouverture et au retour dans l'appli
  const { data: settings } = useSettings()
  // Nouveau compte ou nouvelle installation : assistant de premier démarrage d'abord
  if (settings?.onboarding === 'pending') {
    return (
      <Suspense fallback={<Splash />}>
        <Onboarding />
      </Suspense>
    )
  }
  return (
    <Suspense fallback={<Splash />}>
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Discover />} />
        <Route path="upcoming" element={<Upcoming />} />
        <Route path="news" element={<News />} />
        <Route path="library" element={<Library />} />
        <Route path="tonight" element={<Tonight />} />
        <Route path="watchlist" element={<Watchlist />} />
        <Route path="movie/:id" element={<MediaDetail mediaType="movie" />} />
        <Route path="tv/:id" element={<MediaDetail mediaType="tv" />} />
        <Route path="profile" element={<Profile />} />
        <Route path="stats" element={<Stats />} />
        <Route path="admin" element={<Admin />} />
      </Route>
      {/* Le mode swipe est plein écran, hors layout */}
      <Route path="swipe" element={<Swipe />} />
      <Route path="welcome" element={<Onboarding />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </Suspense>
  )
}

// Porte d'entrée : installation, connexion, mot de passe provisoire, puis l'application
export default function App() {
  const qc = useQueryClient()
  const { data: me, error, refetch, isLoading } = useMe()

  // Une requête refusée (session expirée ou révoquée) renvoie à l'écran de connexion
  useEffect(() => {
    const onUnauthorized = () => qc.invalidateQueries({ queryKey: ['me'] })
    window.addEventListener('cinesync:unauthorized', onUnauthorized)
    return () => window.removeEventListener('cinesync:unauthorized', onUnauthorized)
  }, [qc])

  if (isLoading || (!me && !error)) return <Splash />
  if (!me) return <Splash error={error} onRetry={refetch} />
  if (me.setup_required && !me.user) return <Setup me={me} />
  if (!me.user) return <Login me={me} />
  if (me.user.must_change_password) return <ForcePasswordChange me={me} />
  return <AuthedApp />
}
