import { Link } from 'react-router'
import { ArrowRight, Heart, Layers, X } from 'lucide-react'
import HeroCarousel from '../components/media/HeroCarousel'
import MediaRow from '../components/media/MediaRow'
import PlatformFilter, { useMediaFilters } from '../components/media/PlatformFilter'
import Tabs, { MEDIA_OPTIONS } from '../components/ui/Tabs'
import SeenFilter, { useSeenFilterFn } from '../components/ui/SeenFilter'
import MockBanner from '../components/ui/MockBanner'
import EmptyState from '../components/ui/EmptyState'
import { useCharts, useNewOnPlatforms, useSeenFilter, useSettings, useStatus, useSuggestions, useTrending, useWatchlistReleases } from '../hooks/useMedia'
import { useUiStore } from '../store/uiStore'
import { useT } from '../i18n'

function SwipeTile() {
  const t = useT()
  return (
    <Link
      to="/swipe"
      className="group relative mb-9 flex items-center gap-4 overflow-hidden rounded-3xl tint-accent border border-line p-5 transition hover:border-accent/40 md:p-6"
    >
      <div className="relative h-20 w-16 shrink-0">
        <div className="absolute inset-0 -rotate-12 rounded-xl bg-accent/30" />
        <div className="absolute inset-0 rotate-6 rounded-xl bg-accent2/40" />
        <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-accent shadow-lg shadow-accent/30">
          <Layers className="h-7 w-7 text-white" />
        </div>
      </div>
      <div className="flex-1">
        <p className="font-semibold md:text-lg">{t('Découvrir en swipe')}</p>
        <p className="mt-0.5 text-sm text-text2">{t('Un titre à la fois : passe, ajoute ou aime. Tes choix affinent les suggestions.')}</p>
        <div className="mt-2 flex gap-3 text-xs text-text3">
          <span className="inline-flex items-center gap-1">
            <X className="h-3 w-3" /> {t('passer')}
          </span>
          <span className="inline-flex items-center gap-1">
            <Heart className="h-3 w-3" /> {t("j'aime")}
          </span>
        </div>
      </div>
      <ArrowRight className="h-5 w-5 text-text2 transition group-hover:translate-x-1 group-hover:text-accent2" />
    </Link>
  )
}

export default function Discover() {
  const mediaFilter = useUiStore((s) => s.mediaFilter)
  const setMediaFilter = useUiStore((s) => s.setMediaFilter)
  const mediaFilters = useMediaFilters()
  const seenFilter = useUiStore((s) => s.seenFilter)
  const bySeen = useSeenFilterFn()
  // Réglage « ne plus proposer les vus » : sans effet quand on demande explicitement les titres vus
  const hideSeenSetting = useSeenFilter()
  const hideSeen = (items) => bySeen(seenFilter === 'seen' ? items : hideSeenSetting(items))
  const filter = (items) => hideSeen(mediaFilters(items))
  const { data: settings } = useSettings()
  const { data: status } = useStatus()
  const t = useT()

  const trending = useTrending(mediaFilter)
  const suggestions = useSuggestions(mediaFilter)
  const jwOn = !!settings?.justwatch_enabled
  const recentDays = settings?.recent_days ?? 0
  const releases = useWatchlistReleases(recentDays > 0)
  const chartsMovies = useCharts('movie', jwOn && mediaFilter !== 'tv')
  const chartsShows = useCharts('tv', jwOn && mediaFilter !== 'movie')
  const jwNew = useNewOnPlatforms(!!settings?.justwatch_enabled && (settings?.active_platforms?.length || 0) > 0)

  const trendingItems = filter(trending.data?.results)
  const hero = trendingItems.find((i) => i.backdrop) || trendingItems[0]
  // Le titre du carrousel n'est pas répété dans Tendances, sauf avec un filtre vus / pas vus (liste réduite)
  const rest = seenFilter === 'all' ? trendingItems.filter((i) => i !== hero) : trendingItems

  return (
    <div>
      <HeroCarousel fallback={hero} loading={trending.isLoading} />

      <MockBanner show={trending.data?.mock} />

      <div className="mb-8 flex flex-col gap-3 md:flex-row md:items-center">
        <div className="flex items-center gap-2">
          <Tabs value={mediaFilter} onChange={setMediaFilter} options={MEDIA_OPTIONS} />
          <SeenFilter />
        </div>
        <PlatformFilter />
      </div>

      {recentDays > 0 && releases.data?.results?.length > 0 && (
        <MediaRow
          title={t('Vient de sortir dans ta watchlist')}
          subtitle={t('Sorties de ces {n} derniers jours', { n: recentDays })}
          items={filter(releases.data.results)}
        />
      )}

      {trending.error && <EmptyState title={t('Impossible de charger les tendances')} message={trending.error.message} action={t('Vérifier le Profil')} to="/profile" />}

      <MediaRow
        title={t('Tendances')}
        subtitle={t('Les plus regardés cette semaine')}
        items={rest}
        loading={trending.isLoading}
        empty={!trending.isLoading && <p className="py-8 text-sm text-text3">{t('Aucun titre ne correspond à ces filtres.')}</p>}
      />

      {mediaFilter !== 'tv' && (chartsMovies.isLoading || chartsMovies.data?.results?.length > 0) && (
        <MediaRow title={t('Top 10 films du jour')} subtitle={t('Classement JustWatch · {country}', { country: settings?.country_code || '' })} items={hideSeen(chartsMovies.data?.results)} loading={chartsMovies.isLoading} />
      )}
      {mediaFilter !== 'movie' && (chartsShows.isLoading || chartsShows.data?.results?.length > 0) && (
        <MediaRow title={t('Top 10 séries du jour')} subtitle={t('Classement JustWatch · {country}', { country: settings?.country_code || '' })} items={hideSeen(chartsShows.data?.results)} loading={chartsShows.isLoading} />
      )}

      <SwipeTile />

      <MediaRow
        title={t('Suggestions pour toi')}
        subtitle={status?.trakt?.connected ? t('D’après ton historique Trakt et tes coups de cœur') : t('D’après tes coups de cœur — connecte Trakt pour affiner')}
        items={filter(suggestions.data?.results)}
        loading={suggestions.isLoading}
      />

      {jwNew.data?.results?.length > 0 && (
        <MediaRow title={t('Nouveautés sur tes plateformes')} subtitle={t('Arrivés ces 7 derniers jours')} items={filter(jwNew.data.results)} />
      )}
    </div>
  )
}
