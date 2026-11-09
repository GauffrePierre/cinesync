import { Link } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Check, Inbox, Send, Trash2, X } from 'lucide-react'
import Poster from '../media/Poster'
import Button from '../ui/Button'
import { REQUEST_STATUS, requests } from '../../services/requests'
import { useIsAdmin } from '../../hooks/useAuth'
import { relativeTime } from '../../lib/format'
import { toast } from '../../store/uiStore'
import { useT } from '../../i18n'

/**
 * Demandes d'ajout à la bibliothèque du serveur (Plex, Jellyfin ou Emby).
 * scope="mine" (Profil) : les demandes du compte ; il peut retirer celles encore en attente.
 * scope="all" (Espace admin) : la file de tous les comptes, avec les actions de l'administrateur.
 */
export default function RequestsPanel({ scope = 'mine' }) {
  const t = useT()
  const qc = useQueryClient()
  const isAdmin = useIsAdmin()
  const manage = scope === 'all'
  const { data, isLoading } = useQuery({ queryKey: ['requests', scope], queryFn: () => requests.list(scope) })
  const act = useMutation({
    mutationFn: ({ fn }) => fn(),
    onSuccess: (_, { message }) => {
      if (message) toast(message, 'success')
      qc.invalidateQueries({ queryKey: ['requests'] })
      qc.invalidateQueries({ queryKey: ['media'] })
    },
    onError: (e) => toast(e.message, 'error'),
  })

  if (isLoading) return null
  const list = [...(data?.results || [])].sort((a, b) => (a.status === 'pending' ? 0 : 1) - (b.status === 'pending' ? 0 : 1))

  const footer = !manage && (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-text3">
      <span>
        {data?.direct ? t('Tes demandes sont envoyées directement à Seerr.') : t("Tes demandes sont transmises à l'administrateur.")}
      </span>
      {isAdmin && (
        <Link to="/profile?tab=admin&section=requests" className="inline-flex items-center gap-1 text-accent2 hover:underline">
          {t('Voir toutes les demandes')} <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      )}
    </div>
  )

  if (!list.length) {
    return (
      <>
        <div className="flex items-center gap-3 rounded-2xl border border-dashed border-line p-4 text-sm text-text2">
          <Inbox className="h-5 w-5 shrink-0 text-text3" />
          {manage ? t('Aucune demande pour le moment.') : t("Aucune demande. Le bouton « Demander l'ajout » apparaît sur la fiche des titres absents de ta bibliothèque.")}
        </div>
        {footer}
      </>
    )
  }

  return (
    <div>
      <div className="space-y-2">
        {list.map((r) => {
          const st = REQUEST_STATUS[r.status] || REQUEST_STATUS.pending
          const pending = r.status === 'pending'
          return (
            <div key={r.id} className="flex items-center gap-3 rounded-2xl border border-line bg-bg2 p-3">
              <Link to={`/${r.media_type}/${r.tmdb_id}`} className="w-10 shrink-0">
                <Poster src={r.poster} title={r.title} mediaType={r.media_type} rounded="rounded-lg" />
              </Link>
              <div className="min-w-0 flex-1">
                <Link to={`/${r.media_type}/${r.tmdb_id}`} className="block truncate text-sm font-medium hover:text-accent2">
                  {r.title} {r.year && <span className="text-text3">({r.year})</span>}
                </Link>
                <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-text3">
                  <span className={`rounded-md px-1.5 py-0.5 font-medium ${st.cls}`}>{t(st.label)}</span>
                  {manage && r.user_name && <span className="text-text2">{r.user_name}</span>}
                  {relativeTime(r.created_at)}
                </p>
              </div>
              <div className="flex shrink-0 flex-wrap justify-end gap-1">
                {manage && pending && data.seerr && (
                  <Button size="sm" icon={Send} title={t('Envoyer à Seerr')} onClick={() => act.mutate({ fn: () => requests.sendToSeerr(r.id), message: t('Envoyée à Seerr') })}>
                    Seerr
                  </Button>
                )}
                {manage && pending && (
                  <>
                    <Button size="sm" variant="ghost" title={t('Marquer comme ajoutée')} onClick={() => act.mutate({ fn: () => requests.setStatus(r.id, 'available'), message: t('Marquée disponible') })}>
                      <Check className="h-4 w-4" />
                    </Button>
                    <Button size="sm" variant="ghost" title={t('Refuser')} onClick={() => act.mutate({ fn: () => requests.setStatus(r.id, 'declined'), message: t('Demande refusée') })}>
                      <X className="h-4 w-4" />
                    </Button>
                  </>
                )}
                {(manage || pending) && (
                  <Button size="sm" variant="ghost" title={manage ? t('Supprimer') : t('Retirer ma demande')} onClick={() => act.mutate({ fn: () => requests.remove(r.id) })}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </div>
          )
        })}
      </div>
      {footer}
    </div>
  )
}
