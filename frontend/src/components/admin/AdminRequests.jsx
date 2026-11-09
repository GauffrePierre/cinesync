import { useState } from 'react'
import { Bookmark, Inbox } from 'lucide-react'
import Tabs from '../ui/Tabs'
import RequestsPanel from '../profile/RequestsPanel'
import FamilyWatchlists from './FamilyWatchlists'

// Onglet Admin → Demandes : les demandes d'ajout, et les watchlists que la famille a choisi de partager
export default function AdminRequests() {
  const [view, setView] = useState('requests')
  return (
    <div className="space-y-4">
      <Tabs
        size="sm"
        value={view}
        onChange={setView}
        options={[
          { value: 'requests', label: 'Demandes d’ajout', icon: Inbox },
          { value: 'watchlists', label: 'Watchlists', icon: Bookmark },
        ]}
      />
      {view === 'requests' ? <RequestsPanel scope="all" /> : <FamilyWatchlists />}
    </div>
  )
}
