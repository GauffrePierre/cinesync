import { useNavigate } from 'react-router'
import { useIsAdmin } from '../../hooks/useAuth'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, BellOff, CheckCheck, Inbox, RefreshCw, X } from 'lucide-react'
import PlatformBadge from '../ui/PlatformBadge'
import Poster from '../media/Poster'
import { notifications } from '../../services/notifications'
import { relativeTime } from '../../lib/format'
import { toast } from '../../store/uiStore'
import { useT } from '../../i18n'

// Texte dans la langue de l'interface : gabarit + paramètres (le détail d'une panne est lui aussi traduit)
function notificationText(n, t) {
  if (!n.msg_key) return t(n.message)
  const params = { ...(n.msg_params || {}) }
  if (params.detail) params.detail = t(params.detail)
  return t(n.msg_key, params)
}

export default function NotificationPanel({ items, onClose }) {
  const t = useT()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const isAdmin = useIsAdmin()
  const refresh = () => qc.invalidateQueries({ queryKey: ['notifications'] })

  const readAll = useMutation({ mutationFn: notifications.readAll, onSuccess: refresh })
  const remove = useMutation({ mutationFn: notifications.remove, onSuccess: refresh })
  const check = useMutation({
    mutationFn: notifications.checkNow,
    onSuccess: (r) => {
      refresh()
      toast(
        r.skipped ? t(r.skipped) : t('{checked} titre(s) vérifié(s), {created} nouvelle(s) alerte(s)', { checked: r.checked, created: r.created }),
        r.skipped ? 'info' : 'success',
      )
    },
    onError: (e) => toast(e.message, 'error'),
  })

  const open = (n) => {
    notifications.read(n.id).then(refresh)
    onClose()
    navigate(
      n.kind === 'service' ? '/profile' : n.kind === 'request' && isAdmin ? '/admin?tab=requests' : `/${n.media_type}/${n.tmdb_id}`,
    )
  }

  return (
    <div className="fixed inset-x-3 top-16 z-50 overflow-hidden rounded-2xl border border-line bg-bg2 shadow-2xl md:absolute md:inset-x-auto md:right-0 md:top-12 md:w-96">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <p className="font-semibold">{t('Notifications')}</p>
        <div className="flex gap-1">
          <button
            onClick={() => check.mutate()}
            className="rounded-lg p-1.5 text-text2 hover:bg-bg3 hover:text-text"
            title={t('Vérifier maintenant')}
            disabled={check.isPending}
          >
            <RefreshCw className={`h-4 w-4 ${check.isPending ? 'animate-spin' : ''}`} />
          </button>
          <button onClick={() => readAll.mutate()} className="rounded-lg p-1.5 text-text2 hover:bg-bg3 hover:text-text" title={t('Tout marquer comme lu')}>
            <CheckCheck className="h-4 w-4" />
          </button>
        </div>
      </div>
      <div className="max-h-[60vh] overflow-y-auto">
        {items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-6 py-10 text-center text-sm text-text2">
            <BellOff className="h-6 w-6 text-text3" />
            {t('Aucune notification.')}
            <span className="text-xs text-text3">{t('Tu seras prévenu quand un titre de ta watchlist arrive sur une de tes plateformes.')}</span>
          </div>
        ) : (
          items.map((n) => (
            <div key={n.id} className={`group flex gap-3 border-b border-line px-4 py-3 last:border-none ${n.read ? '' : 'bg-accent/5'}`}>
              <button onClick={() => open(n)} className="flex flex-1 gap-3 text-left">
                <div className="w-10 shrink-0">
                  {n.kind === 'service' ? (
                    <span className="flex aspect-square w-10 items-center justify-center rounded-lg bg-red-500/15 text-red-400">
                      <AlertTriangle className="h-5 w-5" />
                    </span>
                  ) : n.kind === 'request' && !n.poster ? (
                    <span className="flex aspect-square w-10 items-center justify-center rounded-lg bg-accent/15 text-accent2">
                      <Inbox className="h-5 w-5" />
                    </span>
                  ) : (
                    <Poster src={n.poster} title={n.title} mediaType={n.media_type} rounded="rounded-lg" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm">{notificationText(n, t)}</p>
                  <div className="mt-1.5 flex items-center gap-2">
                    <span className="flex -space-x-1">
                      {n.platforms.map((p) => (
                        <PlatformBadge key={p.id} provider={p} size="xs" ring={false} />
                      ))}
                    </span>
                    <span className="text-xs text-text3">{relativeTime(n.created_at)}</span>
                    {!n.read && <span className="h-1.5 w-1.5 rounded-full bg-accent" />}
                  </div>
                </div>
              </button>
              <button
                onClick={() => remove.mutate(n.id)}
                className="self-start rounded p-1 text-text3 opacity-0 transition hover:text-text group-hover:opacity-100"
                aria-label={t('Supprimer')}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
