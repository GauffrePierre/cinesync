import { useQuery } from '@tanstack/react-query'
import { Bookmark, EyeOff } from 'lucide-react'
import MediaRow from '../media/MediaRow'
import EmptyState from '../ui/EmptyState'
import Skeleton from '../ui/Skeleton'
import { admin } from '../../services/admin'
import { useT } from '../../i18n'

// Watchlists que les membres ont choisi de partager (Profil → Préférences → Partage) : seulement les titres qu'ils ne
// peuvent pas regarder (ni sur leurs plateformes, ni dans la bibliothèque du serveur). Ceux voulus par plusieurs d'abord.
export default function FamilyWatchlists() {
  const t = useT()
  const { data, isLoading } = useQuery({ queryKey: ['admin', 'watchlists'], queryFn: admin.watchlists, staleTime: 60_000 })
  if (isLoading || !data) return <Skeleton className="h-48 rounded-2xl" />

  const others = data.not_sharing
  const note = others > 0 && (
    <p className="flex items-center gap-2 text-xs text-text3">
      <EyeOff className="h-3.5 w-3.5 shrink-0" />
      {others > 1 ? t('{n} comptes ne partagent pas leur watchlist.', { n: others }) : t('1 compte ne partage pas sa watchlist.')}
    </p>
  )
  if (!data.members.length) {
    return (
      <div className="space-y-3">
        <EmptyState
          icon={Bookmark}
          title={t('Aucune watchlist partagée pour le moment')}
          message={t('Chaque membre peut partager la sienne avec toi : Profil → Préférences → Partage.')}
        />
        {note}
      </div>
    )
  }
  const footer = (i) => (
    <p className="truncate text-[11px] text-text3">
      {i.members ? i.members.join(', ') : i.in_plex ? t('Dans ta bibliothèque, sans accès pour ce compte') : ''}
    </p>
  )
  return (
    <div className="space-y-2">
      <p className="text-sm text-text2">
        {t('Ce que ta famille veut voir mais ne peut regarder ni sur ses plateformes, ni dans ta bibliothèque.')}
      </p>
      {data.shared.length > 0 && <MediaRow title={t('Voulus par plusieurs personnes')} items={data.shared} renderFooter={footer} hideDisliked={false} />}
      {data.members.map((m) => (
        <MediaRow
          key={m.id}
          title={m.name}
          subtitle={
            m.unavailable > 1
              ? t('{n} titres sur {total} hors de sa portée', { n: m.unavailable, total: m.count })
              : t('{n} titre sur {total} hors de sa portée', { n: m.unavailable, total: m.count })
          }
          items={m.items}
          renderFooter={footer}
          hideDisliked={false}
          empty={t('Tout ce qui est dans sa watchlist est déjà accessible')}
        />
      ))}
      {note}
    </div>
  )
}
