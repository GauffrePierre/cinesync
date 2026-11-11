import { useContext } from 'react'
import { DatabaseBackup, Inbox, Server, Users } from 'lucide-react'
import ServerDashboard, { useMediaServers } from '../admin/ServerDashboard'
import UsersPanel from '../admin/UsersPanel'
import AdminRequests from '../admin/AdminRequests'
import BackupsPanel from '../admin/BackupsPanel'
import { SERVER_LABELS } from '../ui/PlatformBadge'
import { useCurrentUser, usePersonal } from '../../hooks/useAuth'
import { useT } from '../../i18n'
import ProfileTabs from './ProfileTabs'
import { SearchContext, fold } from './Section'

// Onglet Admin du Profil : serveur(s) multimédia, comptes, demandes, sauvegardes, chacun dans un sous-onglet
export default function AdminArea({ section, onSection }) {
  const t = useT()
  const personal = usePersonal()
  const user = useCurrentUser()
  const { data: servers = [] } = useMediaServers()
  // Libellé court : le nom du serveur (Plex, Jellyfin, Emby), ou « Serveurs » s'il y en a plusieurs
  const serverLabel = servers.length === 1 ? SERVER_LABELS[servers[0].kind] : servers.length > 1 ? 'Serveurs' : 'Serveur'
  const all = [
    { key: 'server', icon: Server, label: serverLabel, hint: 'Lectures en cours, débit, bibliothèques, statistiques', Panel: ServerDashboard },
    { key: 'users', icon: Users, label: 'Comptes', hint: 'Comptes locaux et comptes Plex, Jellyfin ou Emby autorisés', Panel: UsersPanel },
    { key: 'requests', icon: Inbox, label: 'Demandes', hint: 'Demandes d’ajout et watchlists partagées par la famille', Panel: AdminRequests },
    { key: 'backups', icon: DatabaseBackup, label: 'Sauvegardes', hint: 'Sauvegarde automatique de la base, téléchargement', Panel: BackupsPanel },
  ]
  // Autre administrateur sans l'accès complet : ni tableau de bord du serveur, ni sauvegardes
  const allowed = user?.server_admin === false ? all.filter((p) => p.key !== 'server' && p.key !== 'backups') : all
  const panels = personal ? allowed.filter((p) => p.key === 'server' || p.key === 'backups') : allowed
  // Recherche : la rubrique qui correspond s'affiche d'elle-même
  const query = useContext(SearchContext)
  const keywords = 'admin administration plex jellyfin emby serveur server dashboard comptes accounts famille family utilisateurs users demandes requests sauvegardes backups'
  const match = query ? panels.find((p) => fold(`${t(p.label)} ${t(p.hint)}`).includes(query)) : null
  if (query && !match && !fold(keywords).includes(query)) return null
  const current = match || panels.find((p) => p.key === section) || panels[0]
  const { Panel } = current
  return (
    <section className="mb-10">
      {query && <h2 className="mb-4 text-lg font-semibold">{t('Réglages admin')}</h2>}
      {panels.length > 1 && (
        <ProfileTabs value={current.key} onChange={onSection} options={panels.map(({ key, label, icon }) => ({ value: key, label, icon }))} />
      )}
      <p className="mb-4 mt-3 text-sm text-text2">
        {t(current.hint)}
        {current.key === 'server' && !personal && ` · ${t('Les connexions TMDB, serveur multimédia (Plex, Jellyfin, Emby), Seerr et JustWatch sont partagées par tous les comptes.')}`}
      </p>
      <Panel />
    </section>
  )
}
