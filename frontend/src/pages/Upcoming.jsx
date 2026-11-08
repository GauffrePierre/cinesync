import { useMemo, useState } from 'react'
import { CalendarDays, Clapperboard, LayoutGrid, Sparkles, Tv } from 'lucide-react'
import MediaGrid from '../components/media/MediaGrid'
import PlatformFilter, { useMediaFilters } from '../components/media/PlatformFilter'
import CalendarView from '../components/upcoming/CalendarView'
import Showtimes from '../components/upcoming/Showtimes'
import Tabs, { MEDIA_OPTIONS } from '../components/ui/Tabs'
import Button from '../components/ui/Button'
import MockBanner from '../components/ui/MockBanner'
import EmptyState from '../components/ui/EmptyState'
import { useNewOnPlatforms, useSettings, useUpcoming } from '../hooks/useMedia'
import { useUiStore } from '../store/uiStore'
import { formatMonth, formatShortDate } from '../lib/format'
import { useT } from '../i18n'

const KIND_BADGE = {
  cinema: { label: 'Cinéma', icon: Clapperboard, cls: 'text-amber-500' },
  streaming: { label: 'Streaming', icon: Tv, cls: 'text-sky-400' },
  new: { label: 'Nouveau', icon: Sparkles, cls: 'text-emerald-500' },
}

function KindBadge({ item }) {
  const t = useT()
  const k = KIND_BADGE[item.release_kind]
  if (!k) return null
  const Icon = k.icon
  const providers = item.release_kind === 'new' ? item.providers?.map((p) => p.name).slice(0, 2).join(', ') : null
  return (
    <p className={`mt-0.5 flex items-center gap-1 truncate text-[11px] ${k.cls}`}>
      <Icon className="h-3 w-3 shrink-0" />
      {providers ? t('Sur {providers}', { providers }) : t(k.label)}
      {item.season && <span className="text-text3">· {item.season}</span>}
    </p>
  )
}

function dedupe(items) {
  const seen = new Set()
  return items.filter((i) => {
    const k = `${i.media_type}-${i.id}`
    if (seen.has(k)) return false
    seen.add(k)
    return true
  })
}

// Regroupe par mois (vue grille)
function ByMonth({ items, footer }) {
  const groups = []
  items.forEach((i) => {
    const key = (i.release_date || '').slice(0, 7)
    let g = groups.find((x) => x.key === key)
    if (!g) groups.push((g = { key, items: [] }))
    g.items.push(i)
  })
  return groups.map((g) => (
    <section key={g.key} className="mb-10">
      <h2 className="mb-4 text-lg font-semibold">{formatMonth(`${g.key}-01`)}</h2>
      <MediaGrid items={g.items} meta="date" renderFooter={footer} hideDisliked />
    </section>
  ))
}

export default function Upcoming() {
  const view = useUiStore((s) => s.upcomingView)
  const setView = useUiStore((s) => s.setUpcomingView)
  const mediaFilter = useUiStore((s) => s.mediaFilter)
  const setMediaFilter = useUiStore((s) => s.setMediaFilter)
  const filter = useMediaFilters()
  const { data: settings } = useSettings()
  const jwEnabled = !!settings?.justwatch_enabled && (settings?.active_platforms?.length || 0) > 0
  const cinemas = settings?.cinemas || []
  const [tab, setTab] = useState('all')
  const t = useT()

  const kind = { all: 'all', future: 'all', cinema: 'cinema', streaming: 'streaming' }[tab]
  const upcoming = useUpcoming('all', kind || 'all', tab !== 'new')
  const jwNew = useNewOnPlatforms(jwEnabled && (tab === 'new' || tab === 'all'))

  const releases = useMemo(() => dedupe((upcoming.data?.pages || []).flatMap((p) => p.results)), [upcoming.data])
  const fresh = useMemo(() => (jwNew.data?.results || []).map((i) => ({ ...i, release_kind: 'new', release_date: i.date })), [jwNew.data])

  const tabs = [
    { value: 'all', label: 'Tous' },
    { value: 'future', label: 'Futures sorties' },
    { value: 'cinema', label: 'Sorties cinéma' },
    { value: 'streaming', label: 'Sorties streaming' },
    ...(jwEnabled ? [{ value: 'new', label: 'Nouveautés plateformes' }] : []),
  ]
  const showViewToggle = tab !== 'new'
  const items = filter(releases)
  const footer = (i) => <KindBadge item={i} />

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold md:text-3xl">{t('À venir')}</h1>
          <p className="mt-1 text-sm text-text2">{t('Cinéma, streaming et nouveautés')}{settings ? ` · ${settings.country_code}` : ''}</p>
        </div>
        {showViewToggle && (
          <Tabs
            value={view}
            onChange={setView}
            options={[
              { value: 'grid', label: 'Grille', icon: LayoutGrid },
              { value: 'calendar', label: 'Calendrier', icon: CalendarDays },
            ]}
          />
        )}
      </div>

      <MockBanner show={upcoming.data?.pages?.[0]?.mock} />

      <div className="no-scrollbar -mx-4 mb-4 overflow-x-auto px-4 md:mx-0 md:px-0">
        <Tabs value={tab} onChange={setTab} options={tabs} />
      </div>
      <div className="mb-8 flex flex-col gap-3 md:flex-row md:items-center">
        <Tabs value={mediaFilter} onChange={setMediaFilter} options={MEDIA_OPTIONS} />
        <PlatformFilter />
      </div>

      {tab === 'cinema' && <Showtimes cinemas={cinemas} />}

      {tab === 'new' ? (
        jwNew.error ? (
          <EmptyState title={t('JustWatch indisponible')} message={jwNew.error.message} />
        ) : (
          <>
            <p className="mb-4 text-sm text-text2">{t('Arrivés sur tes plateformes ces 7 derniers jours (JustWatch)')}</p>
            <MediaGrid
              items={filter(fresh)}
              loading={jwNew.isLoading}
              renderFooter={(i) => <p className="truncate text-[11px] text-text3">{[i.season, formatShortDate(i.date)].filter(Boolean).join(' · ')}</p>}
            />
          </>
        )
      ) : upcoming.error ? (
        <EmptyState title={t('Impossible de charger les sorties')} message={upcoming.error.message} action={t('Vérifier le Profil')} to="/profile" />
      ) : view === 'calendar' ? (
        <CalendarView items={tab === 'all' ? [...items, ...filter(fresh)] : items} />
      ) : (
        <>
          {tab === 'cinema' && <h2 className="mb-4 text-lg font-semibold">{t('Prochaines sorties en salles')}</h2>}
          {tab === 'all' && fresh.length > 0 && (
            <section className="mb-10">
              <h2 className="mb-4 text-lg font-semibold">{t('Nouveautés sur tes plateformes')}</h2>
              <MediaGrid items={filter(fresh).slice(0, 14)} renderFooter={footer} hideDisliked />
            </section>
          )}
          {upcoming.isLoading && <MediaGrid loading />}
          <ByMonth items={items} footer={footer} />
          {!upcoming.isLoading && items.length === 0 && <EmptyState icon={CalendarDays} title={t('Aucune sortie ne correspond à ces filtres')} />}
        </>
      )}

      {tab !== 'new' && upcoming.hasNextPage && (
        <div className="mt-6 flex justify-center">
          <Button onClick={() => upcoming.fetchNextPage()} loading={upcoming.isFetchingNextPage}>
            {t('Charger plus de sorties')}
          </Button>
        </div>
      )}
    </div>
  )
}
