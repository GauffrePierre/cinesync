import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Film, Table2, Tv } from 'lucide-react'
import Tabs from '../components/ui/Tabs'
import Skeleton from '../components/ui/Skeleton'
import EmptyState from '../components/ui/EmptyState'
import { ColumnChart, DataTable, Legend, RankedBars, StatTile } from '../components/stats/Charts'
import { user } from '../services/user'
import { currentLocale, fmtNumber, t as tx, useT } from '../i18n'

const TZ = -new Date().getTimezoneOffset() // minutes à ajouter à l'UTC pour l'heure locale
const PERIODS = [
  { value: 'day', label: 'Jour' },
  { value: 'week', label: 'Semaine' },
  { value: 'month', label: 'Mois' },
  { value: 'year', label: 'Année' },
]
const WEEKDAYS = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
const SERIES = [
  { key: 'episodes', label: 'Épisodes', color: 'var(--series-2)' },
  { key: 'movies', label: 'Films', color: 'var(--series-1)' },
]
const HOURS_SERIES = [{ key: 'hours', label: 'Heures', color: 'var(--series-1)' }]

const d = (iso) => new Date(`${iso}T12:00:00`)
const fmtDate = (iso, opts) => new Intl.DateTimeFormat(currentLocale(), opts).format(d(iso))

function bucketLabels(period, iso) {
  if (period === 'day') return { label: fmtDate(iso, { day: 'numeric' }), sub: fmtDate(iso, { weekday: 'long', day: 'numeric', month: 'long' }) }
  if (period === 'week') return { label: fmtDate(iso, { day: 'numeric', month: 'short' }), sub: tx('Semaine du {date}', { date: fmtDate(iso, { day: 'numeric', month: 'long', year: 'numeric' }) }) }
  if (period === 'month') return { label: fmtDate(iso, { month: 'short' }), sub: fmtDate(iso, { month: 'long', year: 'numeric' }) }
  return { label: iso.slice(0, 4), sub: tx('Année {year}', { year: iso.slice(0, 4) }) }
}

function nextStart(period, iso) {
  const x = d(iso)
  if (period === 'day') x.setDate(x.getDate() + 1)
  else if (period === 'week') x.setDate(x.getDate() + 7)
  else if (period === 'month') x.setMonth(x.getMonth() + 1)
  else x.setFullYear(x.getFullYear() + 1)
  return x.toISOString().slice(0, 10)
}

function Card({ title, sub, children, right }) {
  return (
    <section className="min-w-0 rounded-2xl border border-line bg-bg2 p-4 md:p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="font-semibold">{title}</h2>
          {sub && <p className="text-xs text-text2">{sub}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  )
}

function Details({ period, bucket }) {
  const start = bucket.start
  const end = nextStart(period, start)
  const { data, isLoading } = useQuery({ queryKey: ['stats-events', start, end], queryFn: () => user.statsEvents(start, end, TZ) })
  const list = data?.results || []
  const t = useT()
  return (
    <Card title={bucketLabels(period, start).sub} sub={list.length > 1 ? t('{n} visionnages', { n: list.length }) : t('{n} visionnage', { n: list.length })}>
      {isLoading ? (
        <Skeleton className="h-24" />
      ) : list.length === 0 ? (
        <p className="text-sm text-text3">{t('Rien de regardé sur cette période.')}</p>
      ) : (
        <ul className="max-h-80 divide-y divide-line overflow-y-auto">
          {list.map((e, i) => {
            const path = e.tmdb_id ? `/${e.kind === 'movie' ? 'movie' : 'tv'}/${e.tmdb_id}` : null
            const label = e.kind === 'movie' ? e.title : `${e.show_title} · S${String(e.season ?? '?').padStart(2, '0')}E${String(e.episode ?? '?').padStart(2, '0')}`
            return (
              <li key={i} className="flex items-center gap-3 py-2 text-sm">
                {e.kind === 'movie' ? <Film className="h-4 w-4 shrink-0 text-text3" /> : <Tv className="h-4 w-4 shrink-0 text-text3" />}
                <span className="min-w-0 flex-1 truncate">{path ? <Link to={path} className="hover:text-accent2">{label}</Link> : label}</span>
                <span className="shrink-0 text-xs text-text3">
                  {new Intl.DateTimeFormat(currentLocale(), { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(e.watched_at))}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}

export default function Stats() {
  const [period, setPeriod] = useState('week')
  const [offset, setOffset] = useState(0)
  const [metric, setMetric] = useState('count')
  const [table, setTable] = useState(false)
  const [selected, setSelected] = useState(null)
  const t = useT()
  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ['stats-activity', period, offset],
    queryFn: () => user.statsActivity(period, offset, TZ),
    placeholderData: (prev) => prev, // le rendu précédent reste affiché pendant le rechargement
  })

  const changePeriod = (p) => {
    setPeriod(p)
    setOffset(0)
    setSelected(null)
  }

  const columns = useMemo(
    () =>
      (data?.buckets || []).map((b) => ({
        ...bucketLabels(period, b.start),
        values: { movies: b.movies, episodes: b.episodes, hours: Math.round((b.minutes / 60) * 10) / 10 },
      })),
    [data, period, t], // t : relibelle les colonnes au changement de langue
  )

  if (error) return <EmptyState title={t('Statistiques indisponibles')} message={error.message} />
  if (isLoading || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  const tot = data.totals
  const win = `${fmtDate(data.window.start, { day: 'numeric', month: 'short', year: 'numeric' })} → ${fmtDate(data.window.end, { day: 'numeric', month: 'short', year: 'numeric' })}`
  const labelEvery = period === 'day' ? 3 : period === 'year' && columns.length > 12 ? 2 : 1
  const totalWatches = tot.movies + tot.episodes
  const series = SERIES.map((x) => ({ ...x, label: t(x.label) }))
  const hoursSeries = HOURS_SERIES.map((x) => ({ ...x, label: t(x.label) }))
  const watchesSeries = [{ key: 'n', label: t('Visionnages'), color: 'var(--series-1)' }]

  return (
    <div className={`transition-opacity ${isFetching ? 'opacity-70' : ''}`}>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold md:text-3xl">{t('Statistiques')}</h1>
        <p className="mt-1 text-sm text-text2">
          {t('Ton historique Plex, Trakt et Letterboxd · {events} visionnages au total, {hours} h', { events: fmtNumber(tot.all_time.events), hours: fmtNumber(tot.all_time.hours) })}
          {tot.all_time.undated > 0 && (
            <span className="text-text3"> · {t('dont {n} sans date précise (imports en masse), comptés dans les totaux mais pas dans les graphiques', { n: fmtNumber(tot.all_time.undated) })}</span>
          )}
        </p>
      </div>

      {/* Filtres : une seule rangée, au-dessus de tout ce qu'ils concernent */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <Tabs value={period} onChange={changePeriod} options={PERIODS} />
        {period !== 'year' && (
          <div className="flex items-center gap-1 rounded-xl border border-line bg-bg2 p-1">
            <button onClick={() => { setOffset((o) => o + 1); setSelected(null) }} disabled={!data.has_more_past} className="rounded-lg p-1.5 text-text2 hover:bg-bg3 hover:text-text disabled:opacity-30" aria-label={t('Période précédente')}>
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="px-2 text-xs text-text2">{win}</span>
            <button onClick={() => { setOffset((o) => Math.max(0, o - 1)); setSelected(null) }} disabled={offset === 0} className="rounded-lg p-1.5 text-text2 hover:bg-bg3 hover:text-text disabled:opacity-30" aria-label={t('Période suivante')}>
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        )}
        <button
          onClick={() => setTable((v) => !v)}
          className={`ml-auto inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-medium transition ${table ? 'border-accent bg-accent/15 text-accent2' : 'border-line text-text2 hover:text-text'}`}
        >
          <Table2 className="h-4 w-4" /> {t('Vue tableau')}
        </button>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
        <StatTile label={t('Heures')} value={fmtNumber(tot.hours)} sub={win} />
        <StatTile label={t('Films')} value={fmtNumber(tot.movies)} />
        <StatTile label={t('Épisodes')} value={fmtNumber(tot.episodes)} sub={tot.shows > 1 ? t('{n} séries', { n: tot.shows }) : t('{n} série', { n: tot.shows })} />
        <StatTile label={t('Jours actifs')} value={tot.active_days} />
        <StatTile label={t('Plus longue série')} value={t('{n} j', { n: tot.all_time.longest_streak })} sub={t("jours consécutifs, tout l'historique")} />
      </div>

      <div className="grid gap-4">
        <Card
          title={metric === 'count' ? t('Visionnages') : t('Heures de visionnage')}
          sub={t('Clique sur une colonne pour voir ce que tu as regardé')}
          right={
            <div className="flex flex-wrap items-center gap-3">
              {metric === 'count' && <Legend items={[...series].reverse()} />}
              <Tabs size="sm" value={metric} onChange={setMetric} options={[{ value: 'count', label: 'Nombre' }, { value: 'hours', label: 'Heures' }]} />
            </div>
          }
        >
          {table ? (
            <DataTable
              columns={[{ key: 'p', label: t('Période') }, { key: 'm', label: t('Films'), numeric: true }, { key: 'e', label: t('Épisodes'), numeric: true }, { key: 'h', label: t('Heures'), numeric: true }]}
              rows={columns.map((c) => ({ p: c.sub, m: c.values.movies, e: c.values.episodes, h: c.values.hours }))}
            />
          ) : (
            <ColumnChart
              data={columns}
              series={metric === 'count' ? series : hoursSeries}
              height={220}
              labelEvery={labelEvery}
              selected={selected}
              onSelect={(i) => setSelected((s) => (s === i ? null : i))}
              ariaLabel={t('Visionnages par période')}
            />
          )}
        </Card>

        {selected != null && data.buckets[selected] && <Details period={period} bucket={data.buckets[selected]} />}

        {totalWatches > 0 && (
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title={t('Jour de la semaine')} sub={t('Nombre de visionnages')}>
              {table ? (
                <DataTable columns={[{ key: 'j', label: t('Jour') }, { key: 'n', label: t('Visionnages'), numeric: true }]} rows={data.weekday.map((n, i) => ({ j: t(WEEKDAYS[i]), n }))} />
              ) : (
                <ColumnChart data={data.weekday.map((n, i) => ({ label: t(WEEKDAYS[i]), values: { n } }))} series={watchesSeries} height={150} ariaLabel={t('Visionnages par jour de la semaine')} />
              )}
            </Card>
            <Card title={t('Heure de la journée')} sub={t('Début des visionnages, heure locale')}>
              {table ? (
                <DataTable columns={[{ key: 'h', label: t('Heure') }, { key: 'n', label: t('Visionnages'), numeric: true }]} rows={data.hour.map((n, i) => ({ h: `${i} h`, n }))} />
              ) : (
                <ColumnChart data={data.hour.map((n, i) => ({ label: `${i}h`, sub: `${i} h – ${i + 1} h`, values: { n } }))} series={watchesSeries} height={150} labelEvery={3} ariaLabel={t('Visionnages par heure')} />
              )}
            </Card>
            <Card title={t('Genres les plus regardés')} sub={t('Films et séries de la période')}>
              {data.top_genres.length ? <RankedBars items={data.top_genres.map((g) => ({ label: g.name, value: g.count }))} /> : <p className="text-sm text-text3">{t('Pas encore de genres.')}</p>}
            </Card>
            <Card title={t('Séries les plus regardées')} sub={t('Épisodes vus sur la période')}>
              {data.top_shows.length ? (
                <RankedBars items={data.top_shows.map((s) => ({ label: s.title, value: s.episodes, tmdb: s.tmdb_id }))} color="var(--series-2)" />
              ) : (
                <p className="text-sm text-text3">{t('Aucune série sur la période.')}</p>
              )}
            </Card>
            {data.top_movies.some((m) => m.count > 1) && (
              <Card title={t('Films revus')} sub={t('Vus plusieurs fois sur la période')}>
                <RankedBars items={data.top_movies.filter((m) => m.count > 1).map((m) => ({ label: m.title, value: m.count }))} />
              </Card>
            )}
            <Card title={t('Tes notes')} sub={t('Répartition de toutes tes notes (sur 10)')}>
              {table ? (
                <DataTable columns={[{ key: 'r', label: t('Note') }, { key: 'n', label: t('Titres'), numeric: true }]} rows={data.ratings.map((r) => ({ r: `${r.rating}/10`, n: r.count }))} />
              ) : (
                <ColumnChart data={data.ratings.map((r) => ({ label: String(r.rating), sub: `${r.rating}/10`, values: { n: r.count } }))} series={[{ key: 'n', label: t('Titres'), color: 'var(--series-1)' }]} height={150} ariaLabel={t('Répartition des notes')} />
              )}
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}
