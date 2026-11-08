import { Navigate, useSearchParams } from 'react-router'
import { Inbox, Server, Users } from 'lucide-react'
import Tabs from '../components/ui/Tabs'
import PlexDashboard from '../components/admin/PlexDashboard'
import UsersPanel from '../components/admin/UsersPanel'
import RequestsPanel from '../components/profile/RequestsPanel'
import { useIsAdmin, usePersonal } from '../hooks/useAuth'
import { useT } from '../i18n'

const TABS = [
  { value: 'plex', label: 'Plex', icon: Server },
  { value: 'users', label: 'Utilisateurs', icon: Users },
  { value: 'requests', label: 'Demandes', icon: Inbox },
]

// Espace administrateur : serveur Plex, comptes de la famille, file des demandes
export default function Admin() {
  const t = useT()
  const isAdmin = useIsAdmin()
  const personal = usePersonal()
  const tabs = personal ? TABS.filter((x) => x.value === 'plex') : TABS
  const [params, setParams] = useSearchParams()
  const tab = tabs.some((x) => x.value === params.get('tab')) ? params.get('tab') : 'plex'
  if (!isAdmin) return <Navigate to="/" replace />

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold md:text-3xl">{t('Espace admin')}</h1>
        <p className="mt-1 text-sm text-text2">{t('Ton serveur Plex, les comptes de la famille et leurs demandes.')}</p>
      </div>
      <div className="no-scrollbar -mx-4 mb-6 overflow-x-auto px-4 md:mx-0 md:px-0">
        {tabs.length > 1 && <Tabs value={tab} onChange={(v) => setParams({ tab: v }, { replace: true })} options={tabs} />}
      </div>
      {tab === 'plex' && <PlexDashboard />}
      {tab === 'users' && <UsersPanel />}
      {tab === 'requests' && <RequestsPanel scope="all" />}
    </div>
  )
}
