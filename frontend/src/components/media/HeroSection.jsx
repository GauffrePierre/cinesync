import { Link } from 'react-router'
import { Eye, Heart, Info, Star, X } from 'lucide-react'
import Button from '../ui/Button'
import PlatformBadge, { PlexBadge } from '../ui/PlatformBadge'
import Skeleton from '../ui/Skeleton'
import WatchlistButton from '../ui/WatchlistButton'
import { useDislike, useItemState, useLike, useMarkWatched, useUnlike, useUnwatch } from '../../hooks/useMedia'
import { detailPath, mediaLabel } from '../../lib/format'
import { useT } from '../../i18n'

// Vu, J'aime, Pas intéressé : mêmes actions que sur les affiches
function Opinion({ item }) {
  const t = useT()
  const st = useItemState(item.media_type, item.id)
  const watched = useMarkWatched()
  const unwatch = useUnwatch()
  const like = useLike()
  const unlike = useUnlike()
  const dislike = useDislike()
  const ref = { mediaType: item.media_type, id: item.id, title: item.title }
  const cls = 'flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border backdrop-blur-md transition hover:-translate-y-0.5 active:scale-95'
  const toggleWatched = () => {
    if (!st.watched) return watched.mutate(ref)
    if (window.confirm(t("Retirer « {title} » de tes titres vus (et de l'historique Trakt / Plex) ?", { title: item.title }))) unwatch.mutate(ref)
  }
  return (
    <>
      <button
        type="button"
        onClick={toggleWatched}
        aria-pressed={st.watched}
        title={st.watched ? t('Marquer comme non vu') : t('Marquer comme vu')}
        aria-label={st.watched ? t('Marquer comme non vu') : t('Marquer comme vu')}
        className={`${cls} ${st.watched ? 'border-emerald-500 bg-emerald-500 text-white' : 'border-line bg-bg3/80 text-text hover:bg-bg3'}`}
      >
        <Eye className="h-5 w-5" />
      </button>
      <button
        type="button"
        onClick={() => (st.liked ? unlike : like).mutate(ref)}
        aria-pressed={st.liked}
        title={st.liked ? t('Retirer des coups de cœur') : t("J'aime")}
        aria-label={st.liked ? t('Retirer des coups de cœur') : t("J'aime")}
        className={`${cls} ${st.liked ? 'border-pink-500 bg-pink-500 text-white' : 'border-line bg-bg3/80 text-text hover:bg-bg3'}`}
      >
        <Heart className={`h-5 w-5 ${st.liked ? 'fill-current' : ''}`} />
      </button>
      <button
        type="button"
        onClick={() => dislike.mutate(ref)}
        title={t('Pas intéressé : ne plus me le proposer')}
        aria-label={t('Pas intéressé : ne plus me le proposer')}
        className={`${cls} border-line bg-bg3/80 text-text hover:bg-bg3`}
      >
        <X className="h-5 w-5" />
      </button>
    </>
  )
}

// Contenu mis en avant, pleine largeur : backdrop + dégradé + actions
export default function HeroSection({ item, loading, label, children }) {
  const t = useT()

  if (loading) return <Skeleton className="-mx-4 -mt-4 mb-8 h-[62vh] max-h-[560px] rounded-none md:-mx-8 md:-mt-6" />
  if (!item) return null

  const hue = [...item.title].reduce((a, c) => a + c.charCodeAt(0), 0) % 360
  return (
    <section className="relative -mx-4 -mt-4 mb-8 h-[62vh] max-h-[560px] min-h-[380px] overflow-hidden md:-mx-8 md:-mt-6">
      {item.backdrop ? (
        <img src={item.backdrop} alt="" className="fade-bottom absolute inset-0 h-full w-full object-cover" />
      ) : (
        <div className="absolute inset-0" style={{ background: `linear-gradient(135deg, hsl(${hue} 50% 28%), hsl(${(hue + 60) % 360} 55% 12%))` }} />
      )}
      <div className="fade-left absolute inset-0" />

      <div className="text-halo absolute inset-x-0 bottom-0 p-4 pb-6 md:p-8 md:pb-10">
        <div className="max-w-xl">
          <p className="mb-2 text-xs font-medium tracking-wide text-text2">{label ?? t('Tendance n°1 cette semaine')}</p>
          <h1 className="text-3xl font-semibold leading-tight text-text drop-shadow md:text-5xl">{item.title}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-text2">
            {item.vote_average > 0 && (
              <span className="inline-flex items-center gap-1">
                <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" />
                {Number(item.vote_average).toFixed(1)}
              </span>
            )}
            {item.year && <span>· {item.year}</span>}
            <span>· {mediaLabel(item.media_type)}</span>
            {(item.in_plex || item.providers?.length > 0) && (
              <span className="ml-1 flex -space-x-1.5">
                {item.in_plex && <PlexBadge size="sm" />}
                {item.providers?.slice(0, 4).map((p) => (
                  <PlatformBadge key={p.id} provider={p} size="sm" />
                ))}
              </span>
            )}
          </div>
          {item.overview && <p className="mt-3 line-clamp-3 hidden text-sm text-text2 sm:block md:text-base">{item.overview}</p>}
          <div className="mt-5 flex flex-wrap gap-2">
            {/* Sur téléphone, un appui sur la tuile ouvre déjà la fiche : la place va aux actions */}
            <Link to={detailPath(item)} className="hidden sm:block">
              <Button variant="primary" size="lg" icon={Info}>
                {t('Voir la fiche')}
              </Button>
            </Link>
            <WatchlistButton item={item} size="lg" />
            <Opinion item={item} />
          </div>
        </div>
      </div>
      {children}
    </section>
  )
}
