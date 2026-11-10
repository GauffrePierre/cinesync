import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { Bookmark, Check, Heart, RefreshCw, Star, Trash2 } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import Poster from '../components/media/Poster'
import Tabs, { MEDIA_OPTIONS } from '../components/ui/Tabs'
import MediaGrid from '../components/media/MediaGrid'
import SeenFilter, { usePageSeen } from '../components/ui/SeenFilter'
import Modal from '../components/ui/Modal'
import StarRating from '../components/ui/StarRating'
import Button from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import Skeleton from '../components/ui/Skeleton'
import PlatformBadge, { PlexBadge } from '../components/ui/PlatformBadge'
import { useLibraryWatchlist, useMarkWatched, useRate, useRemoveFromWatchlist, useSettings } from '../hooks/useMedia'
import { library, SOURCE_LABELS } from '../services/library'
import { toast, useUiStore } from '../store/uiStore'
import { detailPath, mediaLabel, relativeTime } from '../lib/format'
import { sortProviders } from '../lib/platforms'
import { SORT_OPTIONS } from '../lib/sorts'
import { fmtNumber, useT } from '../i18n'

const SOURCE_STYLE = {
  trakt: 'bg-trakt/15 text-trakt',
  plex: 'bg-plex/15 text-plex',
  letterboxd: 'bg-letterboxd/15 text-letterboxd',
  local: 'bg-accent/15 text-accent2',
}

export function SourceChips({ sources = [] }) {
  return (
    <span className="inline-flex flex-wrap gap-1">
      {sources.map((s) => (
        <span key={s} className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${SOURCE_STYLE[s] || 'bg-bg3 text-text2'}`}>
          {SOURCE_LABELS[s] || s}
        </span>
      ))}
    </span>
  )
}

// Sous l'affiche (grille sur téléphone) : où regarder, en une ligne
function AvailabilityLine({ item, active }) {
  const t = useT()
  const providers = sortProviders(item.providers, active)
  const mine = item.in_plex || providers.some((p) => active.includes(p.id))
  return (
    <p className={`mt-0.5 truncate text-[11px] ${mine ? 'text-emerald-500' : 'text-text3'}`}>
      {mine ? t('dispo pour toi') : providers.length ? t('Ailleurs en streaming') : t('Pas disponible en streaming')}
    </p>
  )
}

function Row({ item, active, onRate }) {
  const remove = useRemoveFromWatchlist()
  const watched = useMarkWatched()
  const t = useT()
  const providers = sortProviders(item.providers, active)
  const onMine = item.in_plex || providers.some((p) => active.includes(p.id))
  const ref = { mediaType: item.media_type, id: item.id, title: item.title }

  return (
    <div className="flex min-w-0 gap-3 rounded-2xl border border-line bg-bg2 p-3 md:gap-4">
      <Link to={detailPath(item)} className="w-16 shrink-0 md:w-20">
        <Poster src={item.poster} title={item.title} mediaType={item.media_type} rounded="rounded-xl" />
      </Link>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-start gap-2">
          <Link to={detailPath(item)} className="min-w-0 flex-1 truncate font-medium hover:text-accent2">
            {item.title}
          </Link>
          {item.liked && <Heart className="h-4 w-4 shrink-0 fill-pink-500 text-pink-500" aria-label={t('Coup de cœur')} />}
        </div>
        <p className="text-xs text-text2">
          {[item.year, mediaLabel(item.media_type), item.watched && t('Vu'), item.rating && `${fmtNumber(item.rating / 2)}/5`].filter(Boolean).join(' · ')}
        </p>
        <div className="mt-1">
          <SourceChips sources={item.watchlist_sources} />
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {item.in_plex && <PlexBadge server={item.server} size="sm" />}
          {providers.slice(0, 5).map((p) => (
            <PlatformBadge key={p.id} provider={p} size="sm" ring={false} className={active.length && !active.includes(p.id) ? 'opacity-40' : ''} />
          ))}
          {!item.in_plex && providers.length === 0 && <span className="text-xs text-text3">{t('Pas disponible en streaming')}</span>}
          {onMine && <span className="text-[11px] text-emerald-500">· {t('dispo pour toi')}</span>}
        </div>

        <div className="mt-auto flex flex-wrap gap-1 pt-2">
          <button
            onClick={() => watched.mutate(ref)}
            className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs hover:bg-bg3 ${item.watched ? 'text-emerald-500' : 'text-text2 hover:text-text'}`}
          >
            <Check className="h-3.5 w-3.5" /> {item.watched ? t('Vu') : t('Marquer vu')}
          </button>
          <button onClick={() => onRate(item)} className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-text2 hover:bg-bg3 hover:text-text">
            <Star className={`h-3.5 w-3.5 ${item.rating ? 'fill-amber-400 text-amber-400' : ''}`} /> {item.rating ? `${fmtNumber(item.rating / 2)}/5` : t('Noter')}
          </button>
          <button
            onClick={() => remove.mutate(ref)}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-text2 hover:bg-red-500/10 hover:text-red-400"
          >
            <Trash2 className="h-3.5 w-3.5" /> {t('Retirer')}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Watchlist() {
  const qc = useQueryClient()
  const mediaFilter = useUiStore((s) => s.mediaFilter)
  const setMediaFilter = useUiStore((s) => s.setMediaFilter)
  const { value: seenFilter } = usePageSeen('watchlist')
  const [availability, setAvailability] = useState('all')
  const [sort, setSort] = useState('added')
  const [rating, setRating] = useState(null)
  const { data: settings } = useSettings()
  const rate = useRate()
  const t = useT()
  const active = settings?.active_platforms || []
  const wl = useLibraryWatchlist({ mediaType: mediaFilter, availability, sort, seen: seenFilter })

  const pages = wl.data?.pages || []
  const items = useMemo(() => pages.flatMap((p) => p.results), [pages])
  const first = pages[0]
  const lastPull = first?.last_pull

  const sync = useMutation({
    mutationFn: library.syncNow,
    onSuccess: () => {
      toast(t('Synchronisation terminée'), 'success')
      qc.invalidateQueries({ queryKey: ['watchlist'] })
      qc.invalidateQueries({ queryKey: ['library-keys'] })
    },
    onError: (e) => toast(e.message, 'error'),
  })

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold md:text-3xl">Watchlist</h1>
          <p className="mt-1 text-sm text-text2">
            {first ? (first.total > 1 ? t('{n} titres', { n: first.total }) : t('{n} titre', { n: first.total })) : t('Chargement…')} · {t('Trakt, Plex et SynCiné réunis')}
            {lastPull?.at && <span className="text-text3"> · {t('synchronisé {when}', { when: relativeTime(lastPull.at) })}</span>}
          </p>
        </div>
        <Button size="sm" icon={RefreshCw} loading={sync.isPending} onClick={() => sync.mutate()}>
          {t('Synchroniser')}
        </Button>
      </div>

      <div className="mb-6 flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
        <div className="flex items-center gap-2">
          <Tabs value={mediaFilter} onChange={setMediaFilter} options={MEDIA_OPTIONS} />
          <SeenFilter page="watchlist" />
        </div>
        <div className="flex gap-2">
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="h-10 min-w-0 flex-1 rounded-xl border border-line bg-bg2 px-3 text-sm outline-none focus:border-accent md:flex-none"
            aria-label={t('Trier par')}
          >
            {SORT_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>
                {t('Tri : {label}', { label: t(s.label) })}
              </option>
            ))}
          </select>
          <select
            value={availability}
            onChange={(e) => setAvailability(e.target.value)}
            className="h-10 min-w-0 flex-1 rounded-xl border border-line bg-bg2 px-3 text-sm outline-none focus:border-accent md:flex-none"
            aria-label={t('Disponibilité')}
          >
            <option value="all">{t('Tous les titres')}</option>
            <option value="mine">{t('Dispo pour moi')}</option>
            <option value="none">{t('Introuvables')}</option>
          </select>
        </div>
      </div>

      {first?.pending_scores > 0 && (
        <p className="mb-4 text-xs text-text3">{t('Notes de la critique et du public en cours de récupération ({n} titres restants) : elles se complètent en arrière-plan.', { n: first.pending_scores })}</p>
      )}

      {first?.pending_availability > 0 && availability !== 'all' && (
        <p className="mb-4 text-xs text-text3">{t('Vérification des disponibilités en cours ({n} titres restants) — le filtre se complète au fil du chargement.', { n: first.pending_availability })}</p>
      )}

      {wl.error ? (
        <EmptyState title={t('Watchlist indisponible')} message={wl.error.message} action={t('Vérifier le Profil')} to="/profile?tab=connections" />
      ) : wl.isLoading ? (
        <div className="grid gap-3 lg:grid-cols-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState icon={Bookmark} title={t('Rien ici')} message={t('Ajoute des titres depuis Découvrir, une fiche ou le mode swipe.')} action={t('Découvrir')} to="/" />
      ) : (
        <>
          <div className="md:hidden">
            <MediaGrid items={items} renderFooter={(i) => <AvailabilityLine item={i} active={active} />} />
          </div>
          <div className="hidden gap-3 md:grid lg:grid-cols-2">
            {items.map((i) => (
              <Row key={`${i.media_type}-${i.id}`} item={i} active={active} onRate={setRating} />
            ))}
          </div>
        </>
      )}

      {wl.hasNextPage && (
        <div className="mt-6 flex justify-center">
          <Button onClick={() => wl.fetchNextPage()} loading={wl.isFetchingNextPage}>
            {t('Charger plus')}
          </Button>
        </div>
      )}

      <Modal open={!!rating} onClose={() => setRating(null)} title={rating ? t('Noter « {title} »', { title: rating.title }) : ''}>
        <div className="flex flex-col items-center gap-4 py-2">
          <StarRating
            size="lg"
            value={rating?.rating ? rating.rating / 2 : 0}
            onChange={(stars) => {
              rate.mutate({ mediaType: rating.media_type, id: rating.id, title: rating.title, stars })
              setRating(null)
            }}
          />
          <p className="text-xs text-text3">{t('La note est envoyée à Trakt et Plex (sur 10).')}</p>
        </div>
      </Modal>
    </div>
  )
}
