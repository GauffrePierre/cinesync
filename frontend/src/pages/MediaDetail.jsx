import { useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { Check, ChevronLeft, Clapperboard, Clock, Download, Heart, Play, Star, X } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { REQUEST_STATUS, requests } from '../services/requests'
import { toast } from '../store/uiStore'
import Poster from '../components/media/Poster'
import MediaRow from '../components/media/MediaRow'
import Availability from '../components/media/detail/Availability'
import Trailer from '../components/media/detail/Trailer'
import SeriesTracker from '../components/media/detail/SeriesTracker'
import { Cast, Crew } from '../components/media/detail/People'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import StarRating from '../components/ui/StarRating'
import Skeleton from '../components/ui/Skeleton'
import EmptyState from '../components/ui/EmptyState'
import MockBanner from '../components/ui/MockBanner'
import PlatformBadge, { PlexBadge } from '../components/ui/PlatformBadge'
import {
  useDislike,
  useItemState,
  useLike,
  useUndislike,
  useUnlike,
  useMarkWatched,
  useMediaDetail,
  useRate,
  useSettings,
  useSeenFilter,
} from '../hooks/useMedia'
import { formatDate, formatMoney, formatRuntime, safeUrl } from '../lib/format'
import { fmtNumber, useT } from '../i18n'
import WatchlistButton from '../components/ui/WatchlistButton'
import { SourceChips } from './Watchlist'
import WatchLink from '../components/ui/WatchLink'

function RatingPill({ label, value, sub, color }) {
  return (
    <div className="rounded-xl border border-line bg-bg2/80 px-3 py-2 backdrop-blur-md">
      <p className="text-[10px] font-medium" style={{ color }}>
        {label}
      </p>
      <p className="text-lg font-semibold leading-tight">{value}</p>
      {sub && <p className="text-[10px] text-text3">{sub}</p>}
    </div>
  )
}

// « Demander l'ajout » : via Seerr si connecté, sinon en attente pour l'administrateur
function RequestButton({ d }) {
  const t = useT()
  const qc = useQueryClient()
  const create = useMutation({
    mutationFn: () => requests.create(d),
    onSuccess: (r) => {
      toast(t(r.message || 'Demande déjà en cours'), 'success')
      qc.invalidateQueries({ queryKey: ['media'] })
      qc.invalidateQueries({ queryKey: ['requests'] })
    },
    onError: (e) => toast(e.message, 'error'),
  })
  const seerrState = d.seerr?.configured && ['pending', 'processing', 'partially_available', 'available'].includes(d.seerr.status) ? d.seerr : null
  const req = d.request
  if (seerrState || req) {
    const label = t(seerrState ? seerrState.label : (REQUEST_STATUS[req.status] || REQUEST_STATUS.pending).label)
    const href = safeUrl(seerrState?.url || req?.seerr_url)
    const chip = (
      <span className="ml-1 inline-flex items-center gap-1 rounded-lg bg-seerr/15 px-2 py-1 text-[11px] font-medium text-seerr">
        <Clock className="h-3 w-3" /> {label}
      </span>
    )
    return href ? (
      <a href={href} target="_blank" rel="noreferrer" title={t('Voir dans Seerr')}>
        {chip}
      </a>
    ) : (
      chip
    )
  }
  return (
    <Button
      size="sm"
      variant="primary"
      icon={Download}
      loading={create.isPending}
      onClick={() => create.mutate()}
      className="ml-1 !h-7 !px-2.5"
      title={
        d.in_theaters
          ? d.digital_date
            ? t('Encore au cinéma : la demande sera traitée à sa sortie en numérique (prévue le {date})', { date: formatDate(d.digital_date) })
            : t('Encore au cinéma : la demande sera traitée à sa sortie en numérique')
          : d.seerr?.configured
            ? t('Envoyer une demande à Seerr')
            : t("Demander l'ajout à l'administrateur")
      }
    >
      {d.in_theaters ? t("Demander l'ajout quand il sortira") : t("Demander l'ajout")}
    </Button>
  )
}

function InfoRow({ label, children }) {
  if (!children || (Array.isArray(children) && !children.length)) return null
  return (
    <div>
      <dt className="text-xs text-text3">{label}</dt>
      <dd className="mt-0.5 text-sm">{children}</dd>
    </div>
  )
}

function DetailSkeleton() {
  return (
    <div>
      <Skeleton className="-mx-4 -mt-4 h-[45vh] rounded-none md:-mx-8 md:-mt-6" />
      <div className="mt-6 space-y-3">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-24 w-full" />
      </div>
    </div>
  )
}

export default function MediaDetail({ mediaType }) {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: d, isLoading, error } = useMediaDetail(mediaType, id)
  const hideSeen = useSeenFilter()
  const { data: settings } = useSettings()
  const [rateOpen, setRateOpen] = useState(false)
  // État personnel « en direct » (mis à jour immédiatement après une action)
  const live = useItemState(mediaType, id)

  const like = useLike()
  const unlike = useUnlike()
  const dislike = useDislike()
  const undislike = useUndislike()
  const watched = useMarkWatched()
  const rate = useRate()
  const t = useT()

  if (isLoading) return <DetailSkeleton />
  if (error) return <EmptyState title={t('Fiche introuvable')} message={error.message} action={t("Retour à l'accueil")} to="/" />

  const ref = { mediaType, id: d.id, title: d.title }
  const trakt = d.trakt || {}
  const sc = d.scores || {}
  const st = d.state || {}
  // L'état « en direct » (mis à jour sans attendre les services) prime dès qu'il est chargé
  const inWatchlist = live.loaded ? live.inWatchlist : st.in_watchlist
  const watchedNow = live.loaded ? live.watched : st.watched
  const liked = live.loaded ? live.liked : st.liked
  const disliked = live.loaded ? live.disliked : st.disliked
  const ratingTen = live.loaded ? live.rating : st.rating
  const userStars = ratingTen ? Math.round(ratingTen / 2) : 0
  const ratingSub = [watchedNow ? t('Vu') : t('Pas encore vu'), st.rating_source && { trakt: 'Trakt', plex: 'Plex', letterboxd: 'Letterboxd', local: 'SynCiné' }[st.rating_source]]
    .filter(Boolean)
    .join(' · ')
  const isTv = mediaType === 'tv'
  const meta = [
    d.year,
    d.runtime && (isTv ? t('{n} min / épisode', { n: d.runtime }) : formatRuntime(d.runtime)),
    d.certification,
    d.countries?.slice(0, 2).join(', '),
  ].filter(Boolean)
  // Pas dans Plex : on propose de lire directement sur une de tes plateformes (lien direct JustWatch si dispo)
  const active = settings?.active_platforms || []
  const playOn = !d.plex?.available ? (d.availability?.stream || []).find((p) => active.includes(p.id) && (p.url || d.availability?.link)) : null

  return (
    <div>
      {/* Backdrop */}
      <section className="relative -mx-4 -mt-4 h-[46vh] min-h-[300px] overflow-hidden md:-mx-8 md:-mt-6 md:h-[62vh]">
        {d.backdrop ? (
          <img src={d.backdrop} alt="" className="fade-bottom absolute inset-0 h-full w-full object-cover object-top" />
        ) : (
          <div className="tint-accent-strong fade-bottom absolute inset-0" />
        )}
        <div className="fade-left absolute inset-0 hidden md:block" />
        <button
          onClick={() => navigate(-1)}
          className="absolute left-4 top-4 rounded-full bg-black/40 p-2 text-white backdrop-blur-md hover:bg-black/60 md:left-8"
          aria-label={t('Retour')}
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
      </section>

      {/* En-tête */}
      <div className="relative -mt-36 flex flex-col gap-6 md:-mt-60 md:flex-row md:items-end">
        <div className="w-36 shrink-0 md:w-56">
          <Poster src={d.poster} title={d.title} mediaType={mediaType} className="shadow-2xl shadow-black/50" />
        </div>
        <div className="text-halo min-w-0 flex-1 pb-1">
          <h1 className="text-3xl font-semibold leading-tight md:text-5xl">{d.title}</h1>
          {d.original_title && d.original_title !== d.title && <p className="mt-1 text-sm text-text2">{d.original_title}</p>}
          <p className="mt-2 text-sm text-text2">{meta.join(' · ')}</p>
          {d.genres?.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {d.genres.map((g) => (
                <span key={g} className="rounded-full border border-line bg-bg2 px-2.5 py-0.5 text-xs text-text2">
                  {g}
                </span>
              ))}
            </div>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            {sc.rt_critic != null && (
              <RatingPill
                label={t('Critique')}
                value={`${sc.rt_critic} %`}
                sub={`Rotten Tomatoes · ${t({ certified: 'certifié frais', fresh: 'frais', rotten: 'pourri' }[sc.rt_critic_state])}`}
                color={sc.rt_critic_state === 'rotten' ? '#84cc16' : '#fa320a'}
              />
            )}
            {sc.rt_audience != null && (
              <RatingPill label={t('Public')} value={`${sc.rt_audience} %`} sub="Rotten Tomatoes" color={sc.rt_audience_state === 'spilled' ? '#84cc16' : '#fa320a'} />
            )}
            {sc.imdb != null && <RatingPill label={t('Public · IMDb')} value={sc.imdb.toFixed(1)} sub={t('sur 10')} color="#f5c518" />}
            <RatingPill label={t('Public · TMDB')} value={d.vote_average ? d.vote_average.toFixed(1) : '–'} sub={d.vote_count ? t('{n} votes', { n: fmtNumber(d.vote_count) }) : null} color="#01b4e4" />
            {trakt.rating != null && <RatingPill label={t('Public · Trakt')} value={trakt.rating ? `${Math.round(trakt.rating * 10)} %` : '–'} sub={trakt.votes ? t('{n} votes', { n: fmtNumber(trakt.votes) }) : null} color="var(--trakt)" />}
            <RatingPill label={t('Ta note')} value={userStars ? `${userStars}/5` : '–'} sub={ratingSub} color="var(--accent2)" />
            {d.in_theaters && (
              <div className="flex items-center gap-2 rounded-xl border border-amber-500/40 bg-amber-500/10 px-3 py-2" title={t('Sorti en salles, pas encore en streaming')}>
                <Clapperboard className="h-4 w-4 text-amber-500" />
                <span className="text-xs">
                  {d.digital_date ? t('Au cinéma · en numérique le {date}', { date: formatDate(d.digital_date) }) : t('Au cinéma')}
                </span>
              </div>
            )}
            {d.plex?.configured && (
              <div className="flex items-center gap-2 rounded-xl border border-line bg-bg2/80 px-3 py-2 backdrop-blur-md">
                <PlexBadge size="sm" />
                <span className="text-xs">{d.plex.available ? t('Dans ta bibliothèque') : t('Pas dans Plex')}</span>
                {!d.plex.available && <RequestButton d={d} />}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="mt-6">
        <MockBanner show={d.mock} />
      </div>

      {/* Actions */}
      <div className="mb-8 mt-2 flex flex-wrap gap-2">
        {d.plex?.available && d.plex.url ? (
          <WatchLink href={d.plex.url} appRef={{ mediaType, id: d.id, watchUrl: d.plex.watch_url }}>
            <Button variant="primary" icon={Play} className="!bg-plex !text-black">
              {t('Lire sur Plex')}
            </Button>
          </WatchLink>
        ) : (
          playOn && (
            <WatchLink href={playOn.url || d.availability?.link} title={playOn.url ? t('Ouvre directement la page du titre') : t('Ouvre la page de disponibilité')}>
              <Button variant="primary" className="gap-2 !pl-2">
                <PlatformBadge provider={playOn} size="sm" ring={false} />
                <Play className="h-4 w-4" /> {t('Regarder sur {name}', { name: playOn.name })}
              </Button>
            </WatchLink>
          )
        )}
        <WatchlistButton item={{ media_type: mediaType, id: d.id, title: d.title }} primary={!d.plex?.available && !playOn} />
        <Button icon={Check} loading={watched.isPending} onClick={() => watched.mutate(ref)} className={watchedNow ? '!text-emerald-500' : ''}>
          {watchedNow ? t('Déjà vu') : t('Marquer vu')}
        </Button>
        <Button icon={Star} onClick={() => setRateOpen(true)} className={userStars ? '!text-amber-400' : ''}>
          {userStars ? t('Noté {n}/5', { n: userStars }) : t('Noter')}
        </Button>
        <Button
          onClick={() => (liked ? unlike : like).mutate(ref)}
          loading={like.isPending || unlike.isPending}
          className={liked ? '!border-pink-500/50 !bg-pink-500/10' : ''}
          title={liked ? t('Dans tes coups de cœur') : t("J'aime : alimente tes suggestions")}
        >
          <Heart className={`h-4 w-4 ${liked ? 'fill-pink-500 text-pink-500' : ''}`} />
          {liked ? t('Coup de cœur') : t("J'aime")}
        </Button>
        <Button
          onClick={() => (disliked ? undislike : dislike).mutate(ref)}
          loading={dislike.isPending || undislike.isPending}
          className={disliked ? '!border-red-400/50 !bg-red-500/10 !text-red-400' : ''}
          title={disliked ? t('Masqué de tes suggestions : cliquer pour le rétablir') : t('Pas intéressé : ne plus me le proposer')}
        >
          <X className="h-4 w-4" />
          {disliked ? t('Masqué') : t('Pas intéressé')}
        </Button>
      </div>

      {inWatchlist && st.watchlist_sources?.length > 0 && (
        <p className="-mt-5 mb-8 flex items-center gap-2 text-xs text-text3">
          {t('Dans ta watchlist :')} <SourceChips sources={st.watchlist_sources} />
        </p>
      )}

      {/* Synopsis */}
      <section className="mb-10 max-w-3xl">
        {d.tagline && <p className="mb-2 text-sm italic text-text2">{d.tagline}</p>}
        <p className="leading-relaxed text-text/90">{d.overview || t('Pas de synopsis disponible.')}</p>
      </section>

      {isTv && <SeriesTracker data={d} active={settings?.active_platforms || []} />}
      <Availability data={d} active={settings?.active_platforms || []} />
      <Trailer trailer={d.trailer} backdrop={d.backdrop} />
      <Cast cast={d.cast} />
      <Crew crew={d.crew} />

      {d.collection?.parts?.length > 0 && (
        <MediaRow title={d.collection.name} subtitle={t('Collection')} items={d.collection.parts} />
      )}

      {/* Informations */}
      <section className="mb-10">
        <h2 className="mb-4 text-lg font-semibold">{t('Informations')}</h2>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-4">
          <InfoRow label={t('Titre original')}>{d.original_title}</InfoRow>
          <InfoRow label={t('Langue originale')}>{d.original_language}</InfoRow>
          <InfoRow label={t('Pays')}>{d.countries?.join(', ')}</InfoRow>
          <InfoRow label={isTv ? t('Première diffusion') : t('Sortie')}>{formatDate(d.release_date)}</InfoRow>
          <InfoRow label={t('Statut')}>{d.status}</InfoRow>
          {isTv && <InfoRow label={t('Diffuseur')}>{d.networks?.map((n) => n.name).join(', ')}</InfoRow>}
          <InfoRow label={t('Budget')}>{formatMoney(d.budget)}</InfoRow>
          <InfoRow label={t('Recettes')}>{formatMoney(d.revenue)}</InfoRow>
          <InfoRow label={t('Liens')}>
            {(d.imdb_id || trakt.url || d.homepage) && (
              <span className="flex flex-wrap gap-3">
                {d.imdb_id && (
                  <a className="text-accent2 hover:underline" href={`https://www.imdb.com/title/${d.imdb_id}`} target="_blank" rel="noreferrer">
                    IMDb
                  </a>
                )}
                {trakt.url && (
                  <a className="text-accent2 hover:underline" href={safeUrl(trakt.url)} target="_blank" rel="noreferrer">
                    Trakt
                  </a>
                )}
                <a className="text-accent2 hover:underline" href={`https://www.themoviedb.org/${mediaType}/${d.id}`} target="_blank" rel="noreferrer">
                  TMDB
                </a>
                {d.homepage && (
                  <a className="text-accent2 hover:underline" href={safeUrl(d.homepage)} target="_blank" rel="noreferrer">
                    {t('Site officiel')}
                  </a>
                )}
              </span>
            )}
          </InfoRow>
        </dl>
        {d.keywords?.length > 0 && (
          <div className="mt-5 flex flex-wrap gap-1.5">
            {d.keywords.slice(0, 20).map((k) => (
              <span key={k} className="rounded-full bg-bg3 px-2.5 py-0.5 text-xs text-text2">
                {k}
              </span>
            ))}
          </div>
        )}
      </section>

      <MediaRow title={isTv ? t('Séries similaires') : t('Films similaires')} subtitle={t('Recommandations TMDB')} items={hideSeen(d.recommendations)} />

      <Modal open={rateOpen} onClose={() => setRateOpen(false)} title={t('Noter « {title} »', { title: d.title })}>
        <div className="flex flex-col items-center gap-4 py-2">
          <StarRating
            size="lg"
            value={userStars}
            onChange={(stars) => {
              rate.mutate({ ...ref, stars })
              setRateOpen(false)
            }}
          />
          <p className="text-xs text-text3">{t('Ta note est envoyée à Trakt (convertie sur 10).')}</p>
        </div>
      </Modal>
    </div>
  )
}
