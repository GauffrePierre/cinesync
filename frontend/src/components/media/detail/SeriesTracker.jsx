import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ChevronDown, CheckCheck, Loader2, Play, RotateCcw } from 'lucide-react'
import Poster from '../Poster'
import Button from '../../ui/Button'
import PlatformBadge, { PlexBadge } from '../../ui/PlatformBadge'
import { api } from '../../../services/api'
import { formatShortDate } from '../../../lib/format'
import { toast } from '../../../store/uiStore'
import { useT } from '../../../i18n'
import WatchLink from '../../ui/WatchLink'

const pad = (n) => String(n).padStart(2, '0')
// Date courte, avec l'année si ce n'est pas l'année en cours
const epDate = (d) => (d ? `${formatShortDate(d)}${d.slice(0, 4) !== String(new Date().getFullYear()) ? ` ${d.slice(0, 4)}` : ''}` : '')

function Progress({ value, total, color = 'bg-emerald-500' }) {
  const pct = total ? Math.round((value / total) * 100) : 0
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg3" title={`${value}/${total}`}>
      <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  )
}

function useMark(tmdbId) {
  const t = useT()
  const qc = useQueryClient()
  const key = ['episodes', String(tmdbId)]
  return useMutation({
    mutationFn: ({ episodes, watched }) => api.post('/episodes/mark', { tmdb_id: Number(tmdbId), episodes, watched }),
    onMutate: ({ episodes, watched }) => {
      // Mise à jour immédiate des cases cochées
      const prev = qc.getQueryData(key)
      if (prev) {
        const set = new Set(episodes.map((e) => `${e.season}-${e.episode}`))
        const next = structuredClone(prev)
        for (const s of next.seasons) {
          for (const e of s.episodes) if (set.has(`${s.season_number}-${e.number}`)) e.watched = watched
          s.watched_count = s.episodes.filter((e) => e.watched).length
        }
        qc.setQueryData(key, next)
      }
      return { prev }
    },
    onSuccess: (r, { episodes, watched }) => {
      const failed = Object.entries(r.services || {}).filter(([, v]) => v !== 'ok')
      const ok = Object.entries(r.services || {}).filter(([, v]) => v === 'ok').map(([n]) => (n === 'plex' ? 'Plex' : 'Trakt'))
      const many = episodes.length > 1
      const what = many ? t('{n} épisodes', { n: episodes.length }) : `S${pad(episodes[0].season)}E${pad(episodes[0].episode)}`
      const done = watched ? (many ? t('{what} vus', { what }) : t('{what} vu', { what })) : many ? t('{what} non vus', { what }) : t('{what} non vu', { what })
      toast(failed.length ? t('{what} : échec {details}', { what, details: failed.map(([n, v]) => `${n} (${v})`).join(', ') }) : `${done}${ok.length ? ` · ${ok.join(' + ')}` : ''}`, failed.length ? 'error' : 'success')
    },
    onError: (e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(key, ctx.prev)
      toast(e.message, 'error')
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: key })
      qc.invalidateQueries({ queryKey: ['library-keys'] })
    },
  })
}

function SeasonStatus({ season }) {
  const t = useT()
  const aired = season.aired_count
  const seen = season.watched_count
  const [label, cls] =
    aired === 0
      ? [t('À venir'), 'bg-amber-500/15 text-amber-500']
      : seen >= aired
        ? [season.aired_count < season.episode_count ? t('À jour') : t('Vue'), 'bg-emerald-500/15 text-emerald-500']
        : seen > 0
          ? [t('En cours · {seen}/{aired}', { seen, aired }), 'bg-accent/15 text-accent2']
          : [t('À voir'), 'bg-bg3 text-text2']
  return <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-medium ${cls}`}>{label}</span>
}

function SeasonCard({ tmdbId, season, active, watchUrl }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const mark = useMark(tmdbId)
  const aired = season.episodes.filter((e) => e.aired)
  const allSeen = aired.length > 0 && aired.every((e) => e.watched)
  const refs = (eps) => eps.map((e) => ({ season: season.season_number, episode: e.number }))
  const provs = [...season.providers].sort((a, b) => (active.includes(b.id) ? 1 : 0) - (active.includes(a.id) ? 1 : 0))

  return (
    <div className="rounded-2xl border border-line bg-bg2">
      <div className="flex items-center gap-3 p-3">
        <button onClick={() => setOpen((o) => !o)} className="flex min-w-0 flex-1 items-center gap-3 text-left">
          <div className="w-11 shrink-0">
            <Poster src={season.poster} title={season.name} mediaType="tv" rounded="rounded-lg" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="flex flex-wrap items-center gap-2 font-medium">
              {season.name}
              <SeasonStatus season={season} />
            </p>
            <p className="mb-1.5 text-xs text-text2">
              {t('{seen}/{total} vus', { seen: season.watched_count, total: season.aired_count || season.episode_count })}
              {season.aired_count < season.episode_count && ` · ${t('{n} à venir', { n: season.episode_count - season.aired_count })}`}
            </p>
            <Progress value={season.watched_count} total={season.aired_count || season.episode_count} />
          </div>
        </button>
        <div className="hidden shrink-0 items-center gap-1 sm:flex">
          {season.plex_count > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-plex/15 py-0.5 pl-0.5 pr-2 text-[11px] font-medium text-plex" title={t('Épisodes sur ton Plex')}>
              <PlexBadge size="xs" /> {season.plex_count}/{season.episode_count}
            </span>
          )}
          {provs.slice(0, 3).map((p) => (
            <PlatformBadge key={p.id} provider={p} size="sm" ring={false} className={active.length && !active.includes(p.id) ? 'opacity-40' : ''} />
          ))}
        </div>
        <Button
          size="sm"
          variant={allSeen ? 'ghost' : 'secondary'}
          disabled={!aired.length}
          loading={mark.isPending && mark.variables?.episodes.length > 1}
          onClick={() => mark.mutate({ episodes: refs(aired), watched: !allSeen })}
          title={allSeen ? t('Remettre toute la saison en non vue') : t('Marquer tous les épisodes sortis de la saison comme vus')}
          className={allSeen ? '' : '!border-emerald-500/40'}
        >
          {allSeen ? <RotateCcw className="h-4 w-4" /> : <CheckCheck className="h-4 w-4 text-emerald-500" />}
          <span className="hidden sm:inline">{allSeen ? t('Marquer non vue') : t('Saison vue')}</span>
        </Button>
        <button onClick={() => setOpen((o) => !o)} className="p-1 text-text3" aria-label={open ? t('Replier') : t('Déplier')}>
          <ChevronDown className={`h-5 w-5 transition ${open ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {open && (
        <ol className="divide-y divide-line border-t border-line">
          {season.episodes.map((e, idx) => (
            <li
              key={e.number}
              className={`group flex items-center gap-3 px-3 py-2.5 ${e.watched ? 'bg-emerald-500/[0.06]' : e.aired ? '' : 'opacity-55'}`}
            >
              <button
                disabled={!e.aired}
                onClick={() => mark.mutate({ episodes: refs([e]), watched: !e.watched })}
                className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 transition ${
                  e.watched
                    ? 'border-emerald-500 bg-emerald-500 text-white'
                    : e.aired
                      ? 'border-accent text-transparent hover:bg-accent/15 hover:text-accent2'
                      : 'cursor-not-allowed border-dashed border-text3 text-transparent'
                }`}
                aria-label={t(e.watched ? 'Marquer {code} non vu' : 'Marquer {code} vu', { code: `S${pad(season.season_number)}E${pad(e.number)}` })}
              >
                <Check className="h-3.5 w-3.5" />
              </button>
              <span className="w-7 shrink-0 text-right text-xs font-medium text-text3">{e.number}</span>
              <div className="min-w-0 flex-1">
                <p className={`truncate text-sm ${e.watched ? 'text-text2' : ''}`}>{e.name}</p>
                <p className="text-[11px] text-text3">
                  {e.aired ? epDate(e.air_date) : e.air_date ? t('Diffusion le {date}', { date: epDate(e.air_date) }) : t('Date inconnue')}
                  {e.runtime ? ` · ${e.runtime} min` : ''}
                </p>
                {e.progress != null && e.progress > 0 && (
                  <div className="mt-1 h-1 w-24 overflow-hidden rounded-full bg-bg3">
                    <div className="h-full rounded-full bg-plex" style={{ width: `${e.progress}%` }} />
                  </div>
                )}
              </div>
              {e.aired && !e.watched && (
                <span className="shrink-0 rounded-md bg-accent/15 px-1.5 py-0.5 text-[10px] font-medium text-accent2">{t('À voir')}</span>
              )}
              {!e.aired && (
                <span className="shrink-0 rounded-md bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-500">
                  {e.air_date ? t('À venir · {date}', { date: formatShortDate(e.air_date) }) : t('À venir')}
                </span>
              )}
              {e.aired && !e.watched && idx > 0 && (
                <button
                  onClick={() => mark.mutate({ episodes: refs(season.episodes.slice(0, idx + 1).filter((x) => x.aired && !x.watched)), watched: true })}
                  className="hidden shrink-0 rounded-lg px-2 py-1 text-[11px] text-text2 hover:bg-bg3 hover:text-text group-hover:block"
                  title={t("Marquer comme vus tous les épisodes jusqu'à celui-ci")}
                >
                  {t("Vu jusqu'ici")}
                </button>
              )}
              {e.in_plex ? (
                <WatchLink
                  href={e.plex_url}
                  appRef={{ mediaType: 'tv', id: tmdbId, watchUrl }}
                  className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-plex/15 px-2 py-1 text-[11px] font-medium text-plex hover:bg-plex/25"
                  title={t('Lire cet épisode sur Plex')}
                >
                  <Play className="h-3 w-3 fill-current" /> Plex
                </WatchLink>
              ) : (
                provs[0] && e.aired && <PlatformBadge provider={provs[0]} size="xs" ring={false} />
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

// Saisons et épisodes : progression, disponibilités, lecture d'un épisode précis, mise à jour des vus
export default function SeriesTracker({ data, active = [] }) {
  const t = useT()
  const { data: ep, isLoading } = useQuery({
    queryKey: ['episodes', String(data.id)],
    queryFn: () => api.get(`/episodes/${data.id}`),
    staleTime: 60_000,
  })
  const statusLabel = data.in_production ? t('En cours') : data.status === 'Ended' ? t('Terminée') : data.status === 'Canceled' ? t('Annulée') : data.status
  const next = ep?.next_episode
  const nextCode = data.next_episode ? `S${pad(data.next_episode.season_number)}E${pad(data.next_episode.episode_number)}` : ''

  return (
    <section className="mb-10">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{t('Saisons')}</h2>
          <p className="text-sm text-text2">
            {[
              data.number_of_seasons > 1 ? t('{n} saisons', { n: data.number_of_seasons }) : t('{n} saison', { n: data.number_of_seasons }),
              data.number_of_episodes > 1 ? t('{n} épisodes', { n: data.number_of_episodes }) : t('{n} épisode', { n: data.number_of_episodes }),
              statusLabel,
            ].filter(Boolean).join(' · ')}
          </p>
        </div>
        {ep && (
          <div className="w-full max-w-xs">
            <p className="mb-1 text-right text-xs text-text2">
              {t('{seen}/{total} épisodes vus', { seen: ep.totals.watched, total: ep.totals.aired })}
            </p>
            <Progress value={ep.totals.watched} total={ep.totals.aired} />
          </div>
        )}
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-4 text-[11px] text-text2">
        <span className="inline-flex items-center gap-1.5">
          <span className="flex h-3.5 w-3.5 items-center justify-center rounded-full bg-emerald-500 text-white">
            <Check className="h-2.5 w-2.5" />
          </span>
          {t('Vu')}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-3.5 w-3.5 rounded-full border-2 border-accent" /> {t('Sorti, à voir')}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-3.5 w-3.5 rounded-full border-2 border-dashed border-text3" /> {t('Pas encore sorti')}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Play className="h-3 w-3 fill-plex text-plex" /> {t('Sur ton Plex')}
        </span>
      </div>

      {next && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-2xl border border-accent/30 bg-accent/10 px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs text-text2">{t('Prochain épisode à voir')}</p>
            <p className="truncate font-medium">
              S{pad(next.season)}E{pad(next.episode)} · {next.name}
            </p>
          </div>
          {next.plex_url && (
            <WatchLink href={next.plex_url} appRef={{ mediaType: 'tv', id: data.id, watchUrl: data.plex?.watch_url }}>
              <Button size="sm" variant="primary" icon={Play} className="!bg-plex !text-black">
                {next.progress ? t('Reprendre sur Plex') : t('Lire sur Plex')}
              </Button>
            </WatchLink>
          )}
        </div>
      )}
      {data.next_episode && (
        <p className="mb-3 text-xs text-text3">
          {data.next_episode.air_date
            ? t('Prochaine diffusion : {code} le {date}', { code: nextCode, date: formatShortDate(data.next_episode.air_date) })
            : t('Prochaine diffusion : {code}', { code: nextCode })}
        </p>
      )}

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-text3" />
        </div>
      ) : (
        <div className="grid gap-2">
          {ep?.seasons.map((s) => (
            <SeasonCard key={s.season_number} tmdbId={data.id} season={s} active={active} watchUrl={data.plex?.watch_url} />
          ))}
        </div>
      )}
      {ep && !ep.sources.trakt && !ep.sources.plex && (
        <p className="mt-3 text-xs text-text3">{t('Connecte Trakt ou Plex pour suivre les épisodes vus.')}</p>
      )}
    </section>
  )
}
