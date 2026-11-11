import { SERVER_LABELS } from '../ui/PlatformBadge'
import { useT } from '../../i18n'

// Membre : services fournis par le serveur (réglés par l'administrateur, rien à configurer de son côté)
export default function ServerServices({ user, status }) {
  const t = useT()
  const rows = [
    { key: 'tmdb', color: '#01b4e4', label: 'TMDB', on: status?.tmdb?.configured, desc: t('Fiches, tendances, sorties et disponibilités streaming') },
    { key: 'justwatch', color: 'var(--justwatch)', label: 'JustWatch', on: status?.justwatch?.configured, desc: t('Liens directs vers chaque plateforme et nouveautés') },
    status?.plex?.configured && {
      key: 'plex',
      color: 'var(--plex)',
      label: 'Plex',
      on: true,
      desc: user.plex
        ? t('Compte {name} · serveur {server}', { name: user.plex.username, server: status?.plex?.server || '—' })
        : t('Serveur {server}, partagé par l’administrateur', { server: status?.plex?.server || '—' }),
      note: !status?.plex?.own && t('Connecte-toi avec Plex pour synchroniser tes propres vus et ta progression.'),
    },
    status?.jellyfin?.configured && !status?.plex?.configured && {
      key: 'jellyfin',
      color: '#aa5cc3',
      label: SERVER_LABELS[status.jellyfin.kind] || 'Jellyfin',
      on: true,
      desc: status.jellyfin.linked
        ? t('Compte {name} · serveur {server}', { name: status.jellyfin.username, server: status.jellyfin.server || '—' })
        : t('Serveur {server}, partagé par l’administrateur', { server: status.jellyfin.server || '—' }),
    },
    // Demandes d'ajout au serveur multimédia : seulement pour les comptes qui y sont reliés
    status?.seerr?.configured && status?.media?.configured && {
      key: 'seerr',
      color: 'var(--seerr)',
      label: 'Seerr',
      on: true,
      desc: user.can_request_direct ? t('Tes demandes d’ajout partent directement à Seerr') : t('Tes demandes d’ajout passent par l’administrateur'),
    },
  ].filter(Boolean)
  return (
    <div className="rounded-2xl border border-line bg-bg2 p-4">
      <p className="font-medium">{t('Fournis par le serveur')}</p>
      <p className="mt-0.5 text-xs text-text2">{t('Réglés par l’administrateur pour tout le monde : déjà actifs pour toi, rien à configurer.')}</p>
      <ul className="mt-3 divide-y divide-line">
        {rows.map((r) => (
          <li key={r.key} className="flex items-start gap-3 py-2.5 last:pb-0">
            <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-semibold text-white" style={{ background: r.color }}>
              {r.label[0]}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">{r.label}</p>
              <p className="text-xs text-text2">{r.desc}</p>
              {r.note && <p className="mt-0.5 text-xs text-text3">{r.note}</p>}
            </div>
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${r.on ? 'bg-emerald-500/15 text-emerald-500' : 'bg-bg3 text-text3'}`}>
              {r.on ? t('Actif') : t('Non activé')}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
