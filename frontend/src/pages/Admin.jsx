import { Navigate, useSearchParams } from 'react-router'

// Ancienne adresse de l'espace admin (liens de notifications déjà envoyées) : renvoie vers l'onglet Admin du Profil
const SECTIONS = { plex: 'server', users: 'users', requests: 'requests', backups: 'backups' }

export default function Admin() {
  const [params] = useSearchParams()
  const section = SECTIONS[params.get('tab')]
  return <Navigate to={`/profile?tab=admin${section ? `&section=${section}` : ''}`} replace />
}
