import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { ArrowRight, Heart, Layers, X } from 'lucide-react'
import HeroCarousel from '../components/media/HeroCarousel'
import SuggestionFeedback from '../components/media/SuggestionFeedback'
import { reasonText } from '../lib/reasons'
import { api } from '../services/api'
import MediaRow from '../components/media/MediaRow'
import PlatformFilter, { useMediaFilters } from '../components/media/PlatformFilter'
import Tabs, { MEDIA_OPTIONS } from '../components/ui/Tabs'
import SeenFilter, { usePageSeen, useSeenFilterFn } from '../components/ui/SeenFilter'
import MockBanner from '../components/ui/MockBanner'
import EmptyState from '../components/ui/EmptyState'
import { useCharts, useNewOnPlatforms, useSettings, useStatus, useSuggestions, useTrending, useWatchlistReleases } from '../hooks/useMedia'
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
  // Filtre vus / pas vus de cet onglet (par défaut « Pas vus » si le réglage « ne plus proposer les vus » est actif)
  const { value: seenFilter } = usePageSeen('discover')
  const hideSeen = useSeenFilterFn('discover')
  const filter = (items) => hideSeen(mediaFilters(items))
  const { data: settings } = useSettings()
  const { data: status } = useStatus()
  const t = useT()

  const trending = useTrending(mediaFilter)
  // « Seulement ce que je peux regarder » : facultatif (désactivé par défaut, pour continuer à découvrir), retenu sur l'appareil
  const [availableOnly, setAvailableOnly] = useState(() => {
    try {
      return localStorage.getItem('syncine.suggestionsAvailable') === '1'
    } catch {
      return false
    }
  })
  const toggleAvailable = (on) => {
    setAvailableOnly(on)
    try {
      localStorage.setItem('syncine.suggestionsAvailable', on ? '1' : '0')
    } catch {
      /* stockage indisponible : le choix vaut pour cette visite */
    }
  }
  const suggestions = useSuggestions(mediaFilter, availableOnly)
  // Membres qui partagent leurs goûts (comme toi) : leurs coups de cœur
  const [familyOnly, setFamilyOnly] = useState([]) // membres choisis (aucun : tous ceux qui partagent)
  const partners = useQuery({ queryKey: ['family-partners'], queryFn: () => api.get('/media/family/partners'), staleTime: 5 * 60_000 })
  const family = useQuery({
    queryKey: ['family', mediaFilter, familyOnly.join(',')],
    queryFn: () => api.get(`/media/family?media_type=${mediaFilter}${familyOnly.length ? `&members=${familyOnly.join(',')}` : ''}`),
    staleTime: 15 * 60_000,
    enabled: partners.data?.results?.length > 0,
  })
  const jwOn = !!settings?.justwatch_enabled
  const recentDays = settings?.recent_days ?? 0
  const releases = useWatchlistReleases(recentDays > 0)
  const chartsMovies = useCharts('movie', jwOn && mediaFilter !== 'tv')
  const chartsShows = useCharts('tv', jwOn && mediaFilter !== 'movie')
  const jwNew = useNewOnPlatforms(!!settings?.justwatch_enabled && (settings?.active_platforms?.length || 0) > 0)

  const trendingItems = filter(trending.data?.results)
  const hero = trendingItems.find((i) => i.backdrop) || trendingItems[0]
  // Le titre du carrousel n'est pas répété dans Tendances, sauf avec un filtre vus / pas vus (liste réduite)
  const rest = seenFilter !== 'seen' ? trendingItems.filter((i) => i !== hero) : trendingItems

  return (
    <div>
      <HeroCarousel fallback={hero} loading={trending.isLoading} />

      <MockBanner show={trending.data?.mock} />

      <div className="mb-8 flex flex-col gap-3 md:flex-row md:items-center">
        <div className="flex items-center gap-2">
          <Tabs value={mediaFilter} onChange={setMediaFilter} options={MEDIA_OPTIONS} />
          <SeenFilter page="discover" />
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

      {trending.error && <EmptyState title={t('Impossible de charger les tendances')} message={trending.error.message} action={t('Vérifier le Profil')} to="/profile?tab=connections" />}

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
        subtitle={t('D’après tes notes, tes coups de cœur et ce que tu as regardé')}
        // Raison en entier sous l'affiche (au-dessus de « plus / moins comme ça ») plutôt que tronquée dans la ligne du titre
        items={filter(suggestions.data?.results)?.map((i) => ({ ...i, why: reasonText(i, t), reason: undefined }))}
        loading={suggestions.isLoading}
        empty={availableOnly ? t('Rien de disponible pour l’instant parmi tes suggestions') : undefined}
        renderFooter={(item) => <SuggestionFeedback item={item} />}
        action={
          <label className="mr-1 flex cursor-pointer items-center gap-1.5 whitespace-nowrap text-xs text-text2">
            <input type="checkbox" checked={availableOnly} onChange={(e) => toggleAvailable(e.target.checked)} className="h-3.5 w-3.5 accent-[var(--accent)]" />
            {t('Seulement ce que je peux regarder')}
          </label>
        }
      />

      <MediaRow
        title={t('La famille a aimé')}
        subtitle={t('Les coups de cœur des membres qui partagent leurs goûts, pas encore vus par toi')}
        items={filter(family.data?.results)?.map((i) => ({ ...i, why: reasonText(i, t), reason: undefined }))}
        renderFooter={(i) => i.why && <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-accent2">{i.why}</p>}
        empty={familyOnly.length ? t('Rien de nouveau de leur côté pour l’instant') : undefined}
        action={
          partners.data?.results?.length > 1 && (
            <div className="mr-1 flex gap-1">
              {partners.data.results.map((p) => {
                const on = familyOnly.includes(p.id)
                return (
                  <button
                    key={p.id}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setFamilyOnly((m) => (on ? m.filter((x) => x !== p.id) : [...m, p.id]))}
                    className={`rounded-full border px-2.5 py-1 text-xs transition ${on ? 'border-accent bg-accent/15 text-accent2' : 'border-line text-text2 hover:text-text'}`}
                  >
                    {p.name}
                  </button>
                )
              })}
            </div>
          )
        }
      />

      {jwNew.data?.results?.length > 0 && (
        <MediaRow title={t('Nouveautés sur tes plateformes')} subtitle={t('Arrivés ces 7 derniers jours')} items={filter(jwNew.data.results)} />
      )}
    </div>
  )
}
