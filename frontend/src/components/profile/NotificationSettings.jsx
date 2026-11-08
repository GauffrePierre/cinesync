import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Clapperboard, RefreshCw, Tv, WifiOff } from 'lucide-react'
import Button from '../ui/Button'
import PushSettings from './PushSettings'
import { useUpdateSettings } from '../../hooks/useMedia'
import { notifications } from '../../services/notifications'
import { toast } from '../../store/uiStore'
import { useT } from '../../i18n'

const KINDS = [
  { key: 'notify_availability', icon: Clapperboard, label: 'Disponibilités', hint: 'Un titre de ta watchlist arrive sur une de tes plateformes (vérifié chaque jour)' },
  { key: 'notify_new_episodes', icon: Tv, label: 'Nouveaux épisodes', hint: 'Une série que tu suis (watchlist, commencée, regardée récemment) a un nouvel épisode' },
  { key: 'notify_services', icon: WifiOff, label: 'Pannes de services', hint: 'Un service connecté (Plex, Trakt…) ne répond plus' },
]

// Réglages des notifications (cloche en haut à droite)
export default function NotificationSettings({ settings }) {
  const t = useT()
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
        <label key={key} className="flex cursor-pointer items-center gap-3 rounded-xl border border-line bg-bg2 px-3 py-3">
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
