import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clapperboard, Film, Folder, Gauge, Home, Info, Loader2, MonitorPlay, Music, Pause, Play, RefreshCw, Server, Tv, Wifi } from 'lucide-react'
import Button from '../ui/Button'
import EmptyState from '../ui/EmptyState'
import Skeleton from '../ui/Skeleton'
import { SERVER_LABELS, ServerLogo } from '../ui/PlatformBadge'
import { admin } from '../../services/admin'
import { relativeTime } from '../../lib/format'
import { toast } from '../../store/uiStore'
import { currentLocale, fmtNumber, useT } from '../../i18n'

const LIB_ICON = { movie: Film, show: Tv, artist: Music }
const STORE_KEY = 'syncine.adminServer'

// Serveurs multimédias reliés (Plex, Jellyfin / Emby) dont l'admin voit le tableau de bord
export const useMediaServers = () => useQuery({ queryKey: ['admin', 'servers'], queryFn: admin.servers, staleTime: 60_000, select: (d) => d.results })

const dashboardQuery = (srv) => ({ queryKey: ['admin', 'dashboard', srv], queryFn: () => admin.dashboard(srv), staleTime: 5_000, refetchIntervalInBackground: false })

function Card({ title, right, children }) {
  return (
    <section className="rounded-2xl border border-line bg-bg2 p-4 md:p-5">
      {(title || right) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="font-semibold">{title}</h2>
          {right}
        </div>
      )}
      {children}
    </section>
  )
}

function Tile({ label, value }) {
  return (
    <div className="rounded-xl bg-bg3/60 px-3 py-2.5">
      <p className="text-xl font-semibold tabular-nums">{value}</p>
      <p className="text-xs text-text2">{label}</p>
    </div>
  )
}

const DECISION = {
  direct: { label: 'Lecture directe', cls: 'bg-emerald-500/15 text-emerald-500' },
  copy: { label: 'Flux direct', cls: 'bg-sky-500/15 text-sky-400' },
  transcode: { label: 'Transcodage', cls: 'bg-amber-500/15 text-amber-500' },
}

const mbps = (v) => (v == null ? null : `${fmtNumber(v, { maximumFractionDigits: 1 })} Mb/s`)

function Session({ s }) {
  const t = useT()
  const playing = s.state === 'playing'
  const d = DECISION[s.transcode] || DECISION.direct
  const tc = s.transcoding
  return (
    <div className="flex gap-3">
      <div className="h-[72px] w-12 shrink-0 overflow-hidden rounded-lg bg-bg3">
        {s.thumb ? <img src={s.thumb} alt="" className="h-full w-full object-cover" loading="lazy" /> : <Clapperboard className="m-auto mt-6 h-5 w-5 text-text3" />}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{s.title}</p>
        {s.detail && <p className="truncate text-xs text-text2">{s.detail}</p>}
        <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-text3">
          <span className="font-medium text-text2">{s.user}</span>
          <span>{[s.player, s.platform].filter(Boolean).join(' · ')}</span>
          <span className="inline-flex items-center gap-1">
            {s.local ? <Home className="h-3 w-3" /> : <Wifi className="h-3 w-3" />} {s.local ? t('Réseau local') : t('À distance')}
          </span>
        </p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px]">
          <span className={`rounded-md px-1.5 py-0.5 font-medium ${d.cls}`}>{t(d.label)}</span>
          {s.transcode !== 'direct' && (
            <span className="text-text3">
              {t('vidéo : {v} · audio : {a}', { v: t(DECISION[s.video]?.label || ''), a: t(DECISION[s.audio]?.label || '') })}
            </span>
          )}
          {tc?.active && (
            <span className="rounded-md bg-bg3 px-1.5 py-0.5 text-text2">
              {[tc.video_codec, tc.hardware ? t('matériel') : t('logiciel'), tc.speed != null && `${fmtNumber(tc.speed)}×`, tc.throttled && t('en avance')]
                .filter(Boolean)
                .join(' · ')}
            </span>
          )}
        </div>
        <p className="mt-1 flex flex-wrap items-center gap-x-2 text-[11px] text-text3">
          <Gauge className="h-3 w-3" />
          {s.bandwidth_mbps != null ? <span className="font-medium tabular-nums text-text2">{mbps(s.bandwidth_mbps)}</span> : <span>{t('débit inconnu')}</span>}
          {s.source_mbps != null && <span className="tabular-nums">{t('fichier : {rate}', { rate: mbps(s.source_mbps) })}</span>}
          {s.quality && <span>{s.quality}</span>}
        </p>
        {s.progress != null && (
          <div className="mt-2 flex items-center gap-2">
            {playing ? <Play className="h-3 w-3 shrink-0 fill-current text-text2" /> : <Pause className="h-3 w-3 shrink-0 text-text3" />}
            <div className="h-1 flex-1 overflow-hidden rounded-full bg-bg3">
              <div className="h-full rounded-full" style={{ width: `${s.progress}%`, background: 'var(--series-1)' }} />
            </div>
            {s.remaining_min != null && <span className="text-[11px] tabular-nums text-text3">{t('{n} min restantes', { n: s.remaining_min })}</span>}
          </div>
        )}
      </div>
    </div>
  )
}

// Lectures par jour : barres simples (une par jour), la plus haute à 100 %
function DailyBars({ days }) {
  const t = useT()
  const max = Math.max(1, ...days.map((d) => d.plays))
  const fmt = new Intl.DateTimeFormat(currentLocale(), { day: 'numeric', month: 'short' })
  return (
    <div>
      <div className="flex h-24 items-end gap-[3px] border-b" style={{ borderColor: 'var(--viz-grid)' }}>
        {days.map((d) => (
          <div
            key={d.date}
            title={`${fmt.format(new Date(d.date))} · ${t('{n} lectures', { n: d.plays })}`}
            className="flex-1 rounded-t-sm"
            style={{ height: `${(d.plays / max) * 100}%`, minHeight: d.plays ? 2 : 0, background: 'var(--series-1)' }}
          />
        ))}
      </div>
      {days.length > 0 && (
        <div className="mt-1 flex justify-between text-[11px] text-text3">
          <span>{fmt.format(new Date(days[0].date))}</span>
          <span>{fmt.format(new Date(days[days.length - 1].date))}</span>
        </div>
      )}
    </div>
  )
}

function Stats({ server }) {
  const t = useT()
  const { data, error } = useQuery({ queryKey: ['admin', 'stats', server.id], queryFn: () => admin.stats(server.id, 30), staleTime: 5 * 60_000 })
  if (error) return null
  if (!data) return <Skeleton className="h-48 rounded-2xl" />
  const maxUser = Math.max(1, ...data.by_user.map((u) => u.plays))
  return (
    <Card title={t('30 derniers jours')}>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Tile label={t('Lectures')} value={fmtNumber(data.plays)} />
        <Tile label={t('Heures')} value={fmtNumber(data.hours)} />
        <Tile label={t('Films')} value={fmtNumber(data.movies)} />
        <Tile label={t('Épisodes')} value={fmtNumber(data.episodes)} />
      </div>
      {data.approx && (
        <p className="mt-3 flex gap-2 text-xs text-text3">
          <Info className="mt-px h-3.5 w-3.5 shrink-0" />
          {t('{server} ne garde que la dernière lecture de chaque titre : un titre revu plusieurs fois compte pour une lecture.', {
            server: SERVER_LABELS[server.kind],
          })}
        </p>
      )}
      {data.plays === 0 ? (
        <p className="mt-4 text-sm text-text2">{t("Aucune lecture dans l'historique importé sur cette période.")}</p>
      ) : (
        <div className="mt-5 grid gap-6 lg:grid-cols-2">
          <div>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-text3">{t('Par jour')}</h3>
            <DailyBars days={data.by_day} />
          </div>
          <div>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-text3">{t('Par compte')}</h3>
            <ul className="space-y-2">
              {data.by_user.map((u) => (
                <li key={u.name} className="text-sm">
                  <div className="mb-1 flex justify-between gap-2">
                    <span className="truncate">{u.name}</span>
                    <span className="tabular-nums text-text2">{fmtNumber(u.plays)}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-bg3">
                    <div className="h-full rounded-full" style={{ width: `${(u.plays / maxUser) * 100}%`, background: 'var(--series-1)' }} />
                  </div>
                </li>
              ))}
            </ul>
          </div>
          {data.top.length > 0 && (
            <div className="lg:col-span-2">
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-text3">{t('Les plus regardés')}</h3>
              <ol className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                {data.top.map((x, i) => (
                  <li key={x.title} className="flex justify-between gap-2">
                    <span className="truncate">
                      <span className="mr-2 tabular-nums text-text3">{i + 1}.</span>
                      {x.title}
                    </span>
                    <span className="shrink-0 tabular-nums text-text2">{fmtNumber(x.plays)}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

function Dashboard({ server: srv }) {
  const t = useT()
  const qc = useQueryClient()
  const label = SERVER_LABELS[srv.kind]
  const { data, error, isLoading } = useQuery({ ...dashboardQuery(srv.id), refetchInterval: 10_000 })
  const scan = useMutation({
    mutationFn: (id) => admin.scan(srv.id, id),
    onSuccess: () => {
      toast(t('Analyse lancée'), 'success')
      setTimeout(() => qc.invalidateQueries({ queryKey: ['admin', 'dashboard', srv.id] }), 1500)
    },
    onError: (e) => toast(e.message, 'error'),
  })

  if (error) return <EmptyState icon={Server} title={t('Serveur {server} indisponible', { server: label })} message={error.message} action={t('Vérifier le Profil')} to="/profile?tab=connections" />
  if (isLoading || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 rounded-2xl" />
        <Skeleton className="h-48 rounded-2xl" />
      </div>
    )
  }

  const { server, sessions, libraries, activities } = data
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex items-center gap-3">
          <ServerLogo server={srv.kind} className="h-11 w-11 rounded-xl" />
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold">{server.name}</p>
            <p className="truncate text-xs text-text2">{[server.version && `${label} ${server.version.split('-')[0]}`, server.platform].filter(Boolean).join(' · ')}</p>
          </div>
          <span className="flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-500">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> {t('En ligne')}
          </span>
        </div>
      </Card>

      <Card
        title={sessions.length > 1 ? t('{n} lectures en cours', { n: sessions.length }) : t('Lectures en cours')}
        right={
          data.totals?.streams > 0 && (
            <span className="text-right text-xs text-text2">
              <span className="font-medium tabular-nums text-text">{mbps(data.totals.bandwidth_mbps)}</span>
              {data.totals.transcodes > 0 && ` · ${data.totals.transcodes > 1 ? t('{n} transcodages', { n: data.totals.transcodes }) : t('1 transcodage')}`}
            </span>
          )
        }
      >
        {sessions.length ? (
          <div className="space-y-4">
            {sessions.map((s) => (
              <Session key={s.id} s={s} />
            ))}
          </div>
        ) : (
          <p className="flex items-center gap-2 text-sm text-text2">
            <MonitorPlay className="h-4 w-4 text-text3" /> {t('Aucune lecture en cours')}
          </p>
        )}
      </Card>

      <Card
        title={t('Bibliothèques')}
        right={
          <Button size="sm" icon={RefreshCw} loading={scan.isPending && scan.variables === undefined} onClick={() => scan.mutate(undefined)}>
            {t('Tout analyser')}
          </Button>
        }
      >
        <ul className="divide-y divide-line">
          {libraries.map((l) => {
            const Icon = LIB_ICON[l.type] || Folder
            return (
              <li key={l.id} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                <Icon className="h-4 w-4 shrink-0 text-text3" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{l.title}</p>
                  <p className="text-xs text-text3">
                    {l.count != null && (l.count > 1 ? t('{n} éléments', { n: fmtNumber(l.count) }) : t('{n} élément', { n: fmtNumber(l.count) }))}
                    {l.scanned_at ? ` · ${t('analysée {when}', { when: relativeTime(new Date(l.scanned_at * 1000).toISOString()) })}` : ''}
                  </p>
                </div>
                {l.refreshing ? (
                  <span className="flex items-center gap-1.5 text-xs text-text2">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> {t('Analyse…')}
                  </span>
                ) : (
                  <Button size="sm" variant="ghost" loading={scan.isPending && scan.variables === l.id} onClick={() => scan.mutate(l.id)}>
                    {t('Analyser')}
                  </Button>
                )}
              </li>
            )
          })}
        </ul>
        {activities.length > 0 && (
          <div className="mt-4 space-y-2 border-t border-line pt-3">
            {activities.map((a, i) => (
              <div key={i} className="text-xs">
                <div className="flex justify-between gap-2">
                  <span className="truncate text-text2">{[a.title, a.subtitle].filter(Boolean).join(' — ')}</span>
                  {a.progress != null && <span className="tabular-nums text-text3">{a.progress} %</span>}
                </div>
                {a.progress != null && (
                  <div className="mt-1 h-1 overflow-hidden rounded-full bg-bg3">
                    <div className="h-full rounded-full" style={{ width: `${a.progress}%`, background: 'var(--series-1)' }} />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Stats server={srv} />
    </div>
  )
}

// Sélecteur de serveur (si plusieurs) : nom, type et nombre de lectures en cours sur chacun
function ServerTab({ server, active, onSelect }) {
  const t = useT()
  // Le serveur affiché se met à jour toutes les 10 s ; les autres toutes les 30 s, pour leur compteur
  const { data } = useQuery({ ...dashboardQuery(server.id), refetchInterval: active ? 10_000 : 30_000 })
  const streams = data?.totals?.streams || 0
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={active}
      className={`flex min-w-0 flex-1 items-center gap-2.5 rounded-xl border px-3 py-2 text-left transition ${
        active ? 'border-text/30 bg-bg3' : 'border-line bg-bg2 hover:bg-bg3'
      }`}
    >
      <ServerLogo server={server.kind} className="h-8 w-8 rounded-lg" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">{server.name}</span>
        <span className="block truncate text-xs text-text3">{SERVER_LABELS[server.kind]}</span>
      </span>
      {streams > 0 && (
        <span className="flex shrink-0 items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-medium tabular-nums text-emerald-500">
          <Play className="h-3 w-3 fill-current" /> {streams}
          <span className="sr-only">{t('Lectures en cours')}</span>
        </span>
      )}
    </button>
  )
}

function readStored() {
  try {
    return localStorage.getItem(STORE_KEY)
  } catch {
    return null
  }
}

// Tableau de bord des serveurs multimédias : un seul serveur → affiché directement ; plusieurs → sélecteur en haut
export default function ServerDashboard() {
  const t = useT()
  const { data: servers, isLoading } = useMediaServers()
  const [selected, setSelected] = useState(readStored)
  if (isLoading || !servers) return <Skeleton className="h-24 rounded-2xl" />
  if (!servers.length) {
    return (
      <EmptyState
        icon={Server}
        title={t('Aucun serveur multimédia relié')}
        message={t('Relie Plex, Jellyfin ou Emby dans Profil → Connexions pour suivre ici les lectures en cours et les bibliothèques.')}
      />
    )
  }
  const current = servers.find((s) => s.id === selected) || servers[0]
  const select = (id) => {
    setSelected(id)
    try {
      localStorage.setItem(STORE_KEY, id)
    } catch {
      /* stockage indisponible : le choix vaut pour cette visite */
    }
  }
  return (
    <div className="space-y-4">
      {servers.length > 1 && (
        <div className="flex gap-2" role="group" aria-label={t('Serveurs multimédias')}>
          {servers.map((s) => (
            <ServerTab key={s.id} server={s} active={s.id === current.id} onSelect={() => select(s.id)} />
          ))}
        </div>
      )}
      <Dashboard key={current.id} server={current} />
    </div>
  )
}
