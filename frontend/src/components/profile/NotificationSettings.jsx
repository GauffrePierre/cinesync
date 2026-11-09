import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Clapperboard, RefreshCw, Tv, WifiOff } from 'lucide-react'
import Button from '../ui/Button'
import { SERVER_LABELS } from '../ui/PlatformBadge'
import PushSettings from './PushSettings'
import { useStatus, useUpdateSettings } from '../../hooks/useMedia'
import { notifications } from '../../services/notifications'
import { toast } from '../../store/uiStore'
import { useT } from '../../i18n'

const KINDS = [
  { key: 'notify_availability', icon: Clapperboard, label: 'Disponibilités', hint: 'Un titre de ta watchlist arrive sur une de tes plateformes (vérifié chaque jour)' },
  { key: 'notify_new_episodes', icon: Tv, label: 'Nouveaux épisodes', hint: 'Une série que tu suis (watchlist, commencée, regardée récemment) a un nouvel épisode' },
  { key: 'notify_services', icon: WifiOff, label: 'Pannes de services', hint: 'Un service connecté (Plex, Trakt…) ne répond plus' },
]

// Quand prévenir : plusieurs choix possibles (au moins un)
const VIA = {
  notify_new_episodes: {
    field: 'notify_episode_via',
    options: [
      { value: 'air', label: 'Dès la diffusion', hint: 'Le jour de sortie de l’épisode, où qu’il soit diffusé' },
      { value: 'platforms', label: 'Quand il est sur mes plateformes', hint: 'Seulement si la série est sur une de tes plateformes' },
      { value: 'plex', label: 'Quand il arrive sur {server}', hint: 'Dès que l’épisode est ajouté au serveur {server}', server: true },
    ],
  },
  notify_availability: {
    field: 'notify_movie_via',
    options: [
      { value: 'platforms', label: 'Sur mes plateformes', hint: 'Le titre arrive sur une de tes plateformes (vérifié chaque jour)' },
      { value: 'plex', label: 'Ajouté sur {server}', hint: 'Le titre arrive dans la bibliothèque {server}', server: true },
    ],
  },
}

function Via({ field, options, settings, update, server }) {
  const t = useT()
  const current = settings?.[field] || []
  const toggle = (value, on) => {
    const next = on ? [...new Set([...current, value])] : current.filter((v) => v !== value)
    if (next.length) update.mutate({ [field]: next })
    else toast(t('Garde au moins un choix'), 'info')
  }
  return (
    <div className="space-y-1 border-t border-line px-3 py-2 pl-11">
      <p className="text-[11px] font-medium uppercase tracking-wide text-text3">{t('Me prévenir')}</p>
      {options.map((o) => (
        <label key={o.value} className="flex cursor-pointer items-start gap-2.5 py-1">
          <input
            type="checkbox"
            checked={current.includes(o.value)}
            onChange={(e) => toggle(o.value, e.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--accent)]"
          />
          <span className="min-w-0">
            <span className="block text-sm">{t(o.label, { server })}</span>
            <span className="block text-xs text-text3">{t(o.hint, { server })}</span>
          </span>
        </label>
      ))}
    </div>
  )
}

// Réglages des notifications (cloche en haut à droite)
export default function NotificationSettings({ settings }) {
  const t = useT()
  const { data: status } = useStatus()
  // « Ajouté sur le serveur » : Plex, Jellyfin ou Emby, selon le serveur du compte
  const server = status?.media?.configured ? SERVER_LABELS[status.media.server] || 'Plex' : null
  const update = useUpdateSettings()
  const qc = useQueryClient()
  const check = useMutation({
    mutationFn: notifications.checkNow,
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['notifications'] })
      toast(
        r.created
          ? r.created > 1
            ? t('{n} nouvelles notifications', { n: r.created })
            : t('{n} nouvelle notification', { n: r.created })
          : t('Rien de nouveau pour le moment'),
        'success',
      )
    },
    onError: (e) => toast(e.message, 'error'),
  })

  return (
    <div className="space-y-2">
      {KINDS.map(({ key, icon: Icon, label, hint }) => (
        <div key={key} className="rounded-xl border border-line bg-bg2">
          <label className="flex cursor-pointer items-center gap-3 px-3 py-3">
            <Icon className="h-5 w-5 shrink-0 text-accent2" />
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium">{t(label)}</span>
              <span className="block text-xs text-text2">{t(hint)}</span>
            </span>
            <input
              type="checkbox"
              checked={settings?.[key] ?? true}
              onChange={(e) => update.mutate({ [key]: e.target.checked })}
              className="h-5 w-5 shrink-0 accent-[var(--accent)]"
            />
          </label>
          {VIA[key] && (settings?.[key] ?? true) && (
            <Via field={VIA[key].field} options={VIA[key].options.filter((o) => !o.server || server)} settings={settings} update={update} server={server} />
          )}
        </div>
      ))}
      <PushSettings />
      <div className="flex flex-wrap items-center gap-3 pt-2">
        <Button size="sm" icon={RefreshCw} loading={check.isPending} onClick={() => check.mutate()}>
          {t('Vérifier maintenant')}
        </Button>
      </div>
    </div>
  )
}
