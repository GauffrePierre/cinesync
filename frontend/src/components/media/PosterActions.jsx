import { Bookmark, Eye, Heart, X } from 'lucide-react'
import {
  useAddToWatchlist,
  useDislike,
  useItemState,
  useLike,
  useMarkWatched,
  useRemoveFromWatchlist,
  useUnlike,
  useUnwatch,
} from '../../hooks/useMedia'
import { useT } from '../../i18n'

/**
 * Raccourcis sur l'affiche (façon JustWatch) : watchlist, vu, j'aime — chacun bascule d'un clic.
 * Visibles au survol sur ordinateur, toujours visibles sur écran tactile ; un état actif reste affiché.
 */
export default function PosterActions({ item }) {
  const t = useT()
  const st = useItemState(item.media_type, item.id)
  const add = useAddToWatchlist()
  const remove = useRemoveFromWatchlist()
  const watched = useMarkWatched()
  const unwatch = useUnwatch()
  const like = useLike()
  const unlike = useUnlike()
  const dislike = useDislike()
  const ref = { mediaType: item.media_type, id: item.id, title: item.title }

  // Les boutons sont dans le lien de la carte : on bloque la navigation
  const act = (fn) => (e) => {
    e.preventDefault()
    e.stopPropagation()
    fn()
  }

  const buttons = [
    {
      key: 'watchlist',
      on: st.inWatchlist,
      icon: Bookmark,
      label: st.inWatchlist ? t('Retirer de la watchlist') : t('Ajouter à la watchlist'),
      onCls: 'bg-accent text-white',
      run: () => (st.inWatchlist ? remove : add).mutate(ref),
    },
    {
      key: 'watched',
      on: st.watched,
      icon: Eye,
      label: st.watched ? t('Marquer comme non vu') : t('Marquer comme vu'),
      onCls: 'bg-emerald-500 text-white',
      run: () => {
        if (!st.watched) return watched.mutate(ref)
        if (window.confirm(t("Retirer « {title} » de tes titres vus (et de l'historique Trakt / Plex) ?", { title: item.title }))) unwatch.mutate(ref)
      },
    },
    {
      key: 'like',
      on: st.liked,
      icon: Heart,
      label: st.liked ? t('Retirer des coups de cœur') : t("J'aime"),
      onCls: 'bg-pink-500 text-white',
      run: () => (st.liked ? unlike : like).mutate(ref),
    },
    {
      key: 'dislike',
      on: false,
      icon: X,
      label: t('Pas intéressé : ne plus me le proposer'),
      onCls: '',
      run: () => dislike.mutate(ref),
    },
  ]
  const anyOn = buttons.some((b) => b.on)

  return (
    <div
      className={`absolute inset-x-0 bottom-0 flex items-end justify-center gap-1.5 pb-2 pt-8 transition-opacity duration-200 [@media(hover:hover)]:group-focus-within:opacity-100 [@media(hover:hover)]:group-hover:opacity-100 ${
        anyOn ? '' : '[@media(hover:hover)]:opacity-0'
      }`}
      style={{ background: 'linear-gradient(to top, rgba(0,0,0,0.7), rgba(0,0,0,0))' }}
    >
      {buttons.map(({ key, on, icon: Icon, label, onCls, run }) => (
        <button
          key={key}
          type="button"
          onClick={act(run)}
          title={label}
          aria-label={label}
          aria-pressed={on}
          className={`flex h-8 w-8 items-center justify-center rounded-full backdrop-blur-md transition hover:scale-110 ${
            on ? onCls : 'bg-black/45 text-white/90 hover:bg-black/65'
          }`}
        >
          <Icon className={`h-4 w-4 ${on ? 'fill-current' : ''}`} />
        </button>
      ))}
    </div>
  )
}
