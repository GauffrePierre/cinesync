import { useState } from 'react'
import { Bookmark, CheckCircle2, Plus, X } from 'lucide-react'
import Button from './Button'
import { useAddToWatchlist, useItemState, useRemoveFromWatchlist } from '../../hooks/useMedia'
import { useT } from '../../i18n'

/**
 * Bouton watchlist à deux états bien distincts.
 * - Absent : « + Watchlist ».
 * - Présent : marque-page plein coloré + « Dans ta watchlist » + coche verte ; au survol : « Retirer ».
 */
export default function WatchlistButton({ item, primary = false, size = 'md' }) {
  const t = useT()
  const { inWatchlist } = useItemState(item.media_type, item.id)
  const add = useAddToWatchlist()
  const remove = useRemoveFromWatchlist()
  const [hover, setHover] = useState(false)
  const ref = { mediaType: item.media_type, id: item.id, title: item.title }

  if (!inWatchlist) {
    return (
      <Button variant={primary ? 'primary' : 'secondary'} size={size} icon={Plus} loading={add.isPending} onClick={() => add.mutate(ref)}>
        Watchlist
      </Button>
    )
  }
  return (
    <Button
      variant="secondary"
      size={size}
      loading={remove.isPending}
      onClick={() => remove.mutate(ref)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      title={t('Cliquer pour retirer de la watchlist')}
      className={`!border-emerald-500/50 !bg-emerald-500/10 ${hover ? '!border-red-400/60 !bg-red-500/10' : ''}`}
    >
      {hover ? (
        <>
          <X className="h-4 w-4 text-red-400" /> {t('Retirer')}
        </>
      ) : (
        <>
          <Bookmark className="h-4 w-4 fill-accent text-accent" />
          {/* Petits écrans : libellé court, pour garder les boutons sur une ligne */}
          <span className="sm:hidden">{t('Watchlist')}</span>
          <span className="hidden sm:inline">{t('Dans ta watchlist')}</span>
          <CheckCircle2 className="h-4 w-4 fill-emerald-500 text-bg" />
        </>
      )}
    </Button>
  )
}

/** Ruban marque-page affiché en coin d'affiche quand le titre est dans la watchlist */
export function WatchlistRibbon({ item }) {
  const t = useT()
  const { inWatchlist } = useItemState(item.media_type, item.id)
  if (!inWatchlist) return null
  return (
    <span className="absolute right-2 top-0 flex h-7 w-5 items-start justify-center rounded-b-sm bg-accent pt-1 shadow-md" title={t('Dans ta watchlist')}>
      <CheckCircle2 className="h-3.5 w-3.5 text-white" />
    </span>
  )
}
