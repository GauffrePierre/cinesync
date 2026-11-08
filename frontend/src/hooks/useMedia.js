// Hooks de données (TanStack Query) — un hook par besoin de page
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { justwatch, media, tmdb } from '../services/tmdb'
import { trakt } from '../services/trakt'
import { keyOf, library, SOURCE_LABELS } from '../services/library'
import { plex } from '../services/plex'
import { user } from '../services/user'
import { search } from '../services/search'
import { notifications } from '../services/notifications'
import { toast } from '../store/uiStore'
import { t } from '../i18n'

// --- Réglages & profil -------------------------------------------------------

export const useSettings = () => useQuery({ queryKey: ['settings'], queryFn: user.settings, staleTime: 60_000 })
export const useStatus = () => useQuery({ queryKey: ['status'], queryFn: user.status, staleTime: 60_000, refetchInterval: 2 * 60_000 })
export const useStats = () => useQuery({ queryKey: ['stats'], queryFn: user.stats })
export const useCountries = () => useQuery({ queryKey: ['countries'], queryFn: user.countries, staleTime: Infinity })
export const useProviderCatalog = (country) =>
  useQuery({ queryKey: ['providers-catalog', country], queryFn: user.providers, staleTime: 3600_000 })
export const useTraktOauth = () => useQuery({ queryKey: ['trakt-oauth'], queryFn: trakt.oauthInfo })

export function useUpdateSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: user.updateSettings,
    onSuccess: (data) => {
      qc.setQueryData(['settings'], data)
      // Les réglages influencent presque toutes les données : on rafraîchit tout
      qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'settings' })
    },
    onError: (e) => toast(e.message, 'error'),
  })
}

// --- Découverte ----------------------------------------------------------------

export const useTrending = (mediaType = 'all') =>
  useQuery({ queryKey: ['trending', mediaType], queryFn: () => tmdb.trending(mediaType) })

export const useHighlights = () => useQuery({ queryKey: ['highlights'], queryFn: media.highlights, staleTime: 15 * 60_000 })

// Sorties récentes de la watchlist (réglage « Découverte ») ; rafraîchies avec l'état personnel
export const useWatchlistReleases = (enabled) =>
  useQuery({ queryKey: ['library-keys', 'releases'], queryFn: media.watchlistReleases, staleTime: 15 * 60_000, enabled })

export const useSuggestions = (mediaType = 'all') =>
  useQuery({ queryKey: ['suggestions', mediaType], queryFn: () => media.suggestions(mediaType), staleTime: 15 * 60_000 })

export const useUpcoming = (mediaType = 'all', kind = 'all', enabled = true) =>
  useInfiniteQuery({
    queryKey: ['upcoming', mediaType, kind],
    queryFn: ({ pageParam }) => tmdb.upcoming(mediaType, pageParam, kind),
    enabled,
    initialPageParam: 1,
    getNextPageParam: (last, pages) => (last.results.length > 0 && pages.length < 5 ? pages.length + 1 : undefined),
  })

export const useShowtimes = (date, enabled) =>
  useQuery({ queryKey: ['showtimes', date], queryFn: () => user.showtimes(date), enabled, staleTime: 15 * 60_000 })

export const useCharts = (mediaType, enabled) =>
  useQuery({ queryKey: ['jw-charts', mediaType], queryFn: () => justwatch.charts(mediaType), enabled, staleTime: 60 * 60_000 })

export const useNewOnPlatforms = (enabled) =>
  useQuery({ queryKey: ['jw-new'], queryFn: () => justwatch.newOnPlatforms(7), enabled, staleTime: 30 * 60_000 })

// --- Bibliothèque Plex -------------------------------------------------------------

export const useLibrary = ({ mediaType, sort, q, seen = 'all' }) =>
  useInfiniteQuery({
    queryKey: ['library', mediaType, sort, q, seen],
    queryFn: ({ pageParam }) => plex.library({ media_type: mediaType, sort, q, seen, page: pageParam, page_size: 48 }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.page * last.page_size < last.total ? last.page + 1 : undefined),
  })

// --- État personnel & actions synchronisées (Trakt + Plex + SynCiné) ----------------------

export const useLibraryKeys = () => useQuery({ queryKey: ['library-keys'], queryFn: library.keys, staleTime: 60_000 })

/**
 * Réglage « Ne plus proposer les titres déjà vus » : filtre (items) => items sans les films vus ni les
 * séries vues et à jour. Clé ['library-keys', 'seen'] : rafraîchie avec l'état personnel.
 */
export function useSeenFilter() {
  const { data: settings } = useSettings()
  const on = !!settings?.hide_seen
  const { data } = useQuery({ queryKey: ['library-keys', 'seen'], queryFn: library.seen, staleTime: 5 * 60_000, enabled: on })
  const seen = on && data ? new Set(data.keys) : null
  return (items) => (seen && items ? items.filter((i) => !seen.has(keyOf(i.media_type, i.id))) : items)
}

/** Statut d'un titre depuis la vue compacte : { inWatchlist, watched, liked, rating } */
export function useItemState(mediaType, id) {
  const { data } = useLibraryKeys()
  const k = keyOf(mediaType, id)
  return {
    loaded: !!data,
    inWatchlist: !!data?.watchlist?.includes(k),
    watched: !!data?.watched?.includes(k),
    liked: !!data?.liked?.includes(k),
    disliked: !!data?.disliked?.includes(k),
    rating: data?.ratings?.[k] || null,
  }
}

export const useLibraryWatchlist = ({ mediaType, availability, sort, seen = 'all' }) =>
  useInfiniteQuery({
    queryKey: ['watchlist', mediaType, availability, sort, seen],
    queryFn: ({ pageParam }) => library.watchlist({ media_type: mediaType, availability, sort, seen, page: pageParam, page_size: 40 }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.page * last.page_size < last.total ? last.page + 1 : undefined),
  })

// Message de résultat : sur quels services l'action a été enregistrée
// (label est déjà traduit ; les erreurs des services sont traduites si connues)
function syncMessage(label, services = {}) {
  const name = (n) => t(SOURCE_LABELS[n] || n)
  const ok = Object.entries(services).filter(([, v]) => v === 'ok').map(([n]) => name(n))
  const failed = Object.entries(services).filter(([, v]) => v !== 'ok')
  if (failed.length) {
    const errors = failed.map(([n, v]) => t('{service} : {error}', { service: name(n), error: t(v) })).join(' ; ')
    return {
      kind: 'error',
      text: ok.length
        ? t('{label} — OK sur {ok}, échec {errors}', { label, ok: ok.join(', '), errors })
        : t('{label} — échec {errors}', { label, errors }),
    }
  }
  return {
    kind: 'success',
    text: ok.length ? t('{label} · {services}', { label, services: ok.join(' + ') }) : t('{label} (dans SynCiné)', { label }),
  }
}

function useLibraryAction(fn, label, patchKeys) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onMutate: (vars) => {
      // Mise à jour immédiate des boutons, avant la réponse des services
      const prev = qc.getQueryData(['library-keys'])
      if (prev && patchKeys) qc.setQueryData(['library-keys'], patchKeys(structuredClone(prev), keyOf(vars.mediaType, vars.id), vars))
      return { prev }
    },
    onSuccess: (res, vars) => {
      const m = syncMessage(typeof label === 'function' ? label(vars) : t(label), res?.services)
      toast(m.text, m.kind)
    },
    onError: (e, _vars, context) => {
      if (context?.prev) qc.setQueryData(['library-keys'], context.prev)
      toast(e.message, 'error')
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['library-keys'] })
      qc.invalidateQueries({ queryKey: ['watchlist'] })
      qc.invalidateQueries({ queryKey: ['media'] })
      qc.invalidateQueries({ queryKey: ['suggestions'] })
      qc.invalidateQueries({ queryKey: ['disliked'] })
    },
  })
}

const addKey = (list, k) => (list.includes(k) ? list : [...list, k])

export const useAddToWatchlist = () =>
  useLibraryAction(
    ({ mediaType, id, title }) => library.addToWatchlist(mediaType, id, title),
    'Ajouté à la watchlist',
    (d, k) => ({ ...d, watchlist: addKey(d.watchlist, k) }),
  )
export const useRemoveFromWatchlist = () =>
  useLibraryAction(
    ({ mediaType, id }) => library.removeFromWatchlist(mediaType, id),
    'Retiré de la watchlist',
    (d, k) => ({ ...d, watchlist: d.watchlist.filter((x) => x !== k) }),
  )
export const useMarkWatched = () =>
  useLibraryAction(
    ({ mediaType, id, title }) => library.markWatched(mediaType, id, title),
    'Marqué comme vu',
    (d, k) => ({ ...d, watched: addKey(d.watched, k) }),
  )
export const useRate = () =>
  useLibraryAction(
    ({ mediaType, id, stars, title }) => library.rate(mediaType, id, stars, title),
    ({ stars }) => t('Noté {stars}/5', { stars }),
    (d, k, v) => ({ ...d, ratings: { ...d.ratings, [k]: v.stars * 2 } }),
  )
export const useLike = () =>
  useLibraryAction(({ mediaType, id, title }) => library.like(mediaType, id, title), "Ajouté à tes coups de cœur", (d, k) => ({ ...d, liked: addKey(d.liked, k) }))

export const useUnwatch = () =>
  useLibraryAction(({ mediaType, id }) => library.unwatch(mediaType, id), 'Retiré des titres vus', (d, k) => ({ ...d, watched: d.watched.filter((x) => x !== k) }))
export const useUnlike = () =>
  useLibraryAction(({ mediaType, id }) => library.unlike(mediaType, id), 'Retiré des coups de cœur', (d, k) => ({ ...d, liked: d.liked.filter((x) => x !== k) }))

export const useDislike = () =>
  useLibraryAction(
    ({ mediaType, id, title }) => library.dislike(mediaType, id, title),
    'Masqué de tes suggestions',
    (d, k) => ({ ...d, disliked: addKey(d.disliked || [], k), liked: d.liked.filter((x) => x !== k) }),
  )
export const useUndislike = () =>
  useLibraryAction(({ mediaType, id }) => library.undislike(mediaType, id), 'De nouveau proposé', (d, k) => ({ ...d, disliked: (d.disliked || []).filter((x) => x !== k) }))

export const useSyncStatus = () => useQuery({ queryKey: ['sync-status'], queryFn: library.syncStatus, refetchInterval: 5 * 60_000 })

// --- Fiche détail ------------------------------------------------------------------

export const useMediaDetail = (mediaType, id) =>
  useQuery({ queryKey: ['media', mediaType, String(id)], queryFn: () => media.full(mediaType, id), enabled: !!id })

// --- Recherche & notifications ---------------------------------------------------------

export const useGlobalSearch = (q) =>
  useQuery({ queryKey: ['search', q], queryFn: () => search.global(q), enabled: q.trim().length >= 2, staleTime: 60_000 })

export const useNotifications = () =>
  useQuery({ queryKey: ['notifications'], queryFn: notifications.list, refetchInterval: 10 * 60_000 })
