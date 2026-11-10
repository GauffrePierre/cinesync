import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Baby, ChevronLeft, ChevronRight, Dices, Info, Play, Popcorn, User, Users } from 'lucide-react'
import MediaRow from '../components/media/MediaRow'
import Poster from '../components/media/Poster'
import Tabs, { MEDIA_OPTIONS } from '../components/ui/Tabs'
import SeenFilter from '../components/ui/SeenFilter'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import EmptyState from '../components/ui/EmptyState'
import PlatformBadge, { PlexBadge, SERVER_LABELS } from '../components/ui/PlatformBadge'
import { api, qs } from '../services/api'
import { useSettings, useStatus } from '../hooks/useMedia'
import { usePersonal } from '../hooks/useAuth'
import { KID_LABELS } from '../lib/kids'
import { detailPath, formatRuntime, mediaLabel } from '../lib/format'
import { currentLocale, t as tx, useT } from '../i18n'
import { TONIGHT_SORTS } from '../lib/sorts'
import { reasonText } from '../lib/reasons'
import WatchLink from '../components/ui/WatchLink'

const DURATIONS = [
  { value: '', label: 'Peu importe' },
  { value: '90', label: '< 1 h 30' },
  { value: '120', label: '< 2 h' },
  { value: '150', label: '< 2 h 30' },
]
const MOODS = [
  { value: '', label: 'Toutes les envies' },
  { value: 'pepites', label: '💎 Pépites méconnues' },
  { value: 'classiques', label: '🎞️ Classiques' },
  { value: 'recents', label: '🆕 Sortis cette année' },
  { value: 'noel', label: '🎄 Noël' },
  { value: 'halloween', label: '🎃 Halloween' },
  { value: 'petits', label: '🧸 Petits (3-6 ans)' },
  { value: 'enfants', label: '🧒 Enfants (7-10 ans)' },
  { value: 'ados', label: '🧑 Ados (11-14 ans)' },
  { value: 'rire', label: '😄 Rire' },
  { value: 'frissons', label: '😰 Suspense' },
  { value: 'peur', label: '😱 Peur' },
  { value: 'enquete', label: '🕵️ Enquête' },
  { value: 'action', label: '💥 Action' },
  { value: 'aventure', label: '🗺️ Aventure' },
  { value: 'evasion', label: '🚀 SF & fantastique' },
  { value: 'animation', label: '🎨 Animation' },
  { value: 'emotion', label: '🥲 Émotion' },
  { value: 'romance', label: '💘 Romance' },
  { value: 'famille', label: '👨‍👩‍👧 Famille' },
  { value: 'histoire', label: '🏛️ Histoire & guerre' },
  { value: 'western', label: '🤠 Western' },
  { value: 'musique', label: '🎵 Musique' },
  { value: 'comprendre', label: '🧠 Documentaire' },
]

// Pastilles sur une ligne : glisser du doigt sur téléphone, flèches (et molette) à la souris
function Chips({ value, onChange, options }) {
  const t = useT()
  const ref = useRef(null)
  const [edges, setEdges] = useState({ left: false, right: false })
  const update = () => {
    const el = ref.current
    if (el) setEdges({ left: el.scrollLeft > 4, right: el.scrollLeft + el.clientWidth < el.scrollWidth - 4 })
  }
  useEffect(() => {
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [options])
  const scroll = (dir) => ref.current?.scrollBy({ left: dir * ref.current.clientWidth * 0.7, behavior: 'smooth' })
  const arrow = 'absolute top-1/2 z-10 hidden h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full border border-line bg-bg2/95 text-text2 shadow hover:text-text md:flex'
  return (
    <div className="relative">
      {edges.left && (
        <button onClick={() => scroll(-1)} className={`${arrow} left-0`} aria-label={t('Précédent')}>
          <ChevronLeft className="h-4 w-4" />
        </button>
      )}
      {edges.right && (
        <button onClick={() => scroll(1)} className={`${arrow} right-0`} aria-label={t('Suivant')}>
          <ChevronRight className="h-4 w-4" />
        </button>
      )}
    <div
      ref={ref}
      onScroll={update}
      onWheel={(e) => {
        if (ref.current && Math.abs(e.deltaY) > Math.abs(e.deltaX)) ref.current.scrollLeft += e.deltaY
      }}
      className={`no-scrollbar -mx-4 flex gap-2 overflow-x-auto scroll-smooth px-4 md:mx-0 ${edges.left || edges.right ? 'md:px-10' : 'md:px-0'}`}
    >
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-medium transition ${
            value === o.value ? 'border-accent bg-accent/15 text-accent2' : 'border-line text-text2 hover:text-text'
          }`}
        >
          {t(o.label)}
        </button>
      ))}
    </div>
    </div>
  )
}

const footer = (i) =>
  i.remaining ? (
    <p className="truncate text-[11px] text-text2">{i.remaining > 1 ? tx('Encore {n} épisodes', { n: i.remaining }) : tx('Encore 1 épisode')}</p>
  ) : i.resume ? (
    <div className="mt-1">
      <p className="truncate text-[11px] text-text2">{tx(i.resume)}</p>
      {i.progress != null && (
        <div className="mt-1 h-1 overflow-hidden rounded-full bg-bg3">
          <div className={`h-full rounded-full ${i.server && i.server !== 'plex' ? 'bg-accent' : 'bg-plex'}`} style={{ width: `${i.progress}%` }} />
        </div>
      )}
    </div>
  ) : i.runtime ? (
    <p className="truncate text-[11px] text-text3">{formatRuntime(i.runtime)}</p>
  ) : null

export default function Tonight() {
  const { data: status } = useStatus()
  const [mediaType, setMediaType] = useState('all')
  const [duration, setDuration] = useState('')
  const [mood, setMood] = useState('')
  const [sort, setSort] = useState('relevance')
  const [seen, setSeen] = useState('unseen') // propre à cette page : par défaut, ce qui n'a pas encore été vu
  const [pickOpen, setPickOpen] = useState(false)
  // Pour qui : membres choisis (ceux qui partagent leurs goûts) et, si déclarés dans Préférences, les enfants du foyer
  const [members, setMembers] = useState([])
  const [withKids, setWithKids] = useState(false)
  const toggleMember = (id) => setMembers((m) => (m.includes(id) ? m.filter((x) => x !== id) : [...m, id]))
  const { data: partners } = useQuery({ queryKey: ['family-partners'], queryFn: () => api.get('/media/family/partners'), staleTime: 5 * 60_000 })
  const { data: settings } = useSettings()
  const personal = usePersonal()
  const t = useT()
  // Enfants du foyer (Préférences) : tranches d'âge affichées dans l'infobulle du bouton
  const kidsLabel = (settings?.family_kids || []).map((k) => t(KID_LABELS[k] || k)).join(', ')
  const active = settings?.active_platforms || []
  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ['tonight', mediaType, duration, mood, sort, seen, members.join(','), withKids],
    // Fuseau de l'appareil : le serveur connaît ainsi le jour de la semaine (habitudes du soir)
    queryFn: () => api.get(`/tonight${qs({ media_type: mediaType, max_runtime: duration, mood, sort, seen, tz_offset_min: -new Date().getTimezoneOffset(), with_users: members.join(',') || undefined, kids: withKids || undefined })}`),
    placeholderData: (prev) => prev,
    staleTime: 10 * 60_000,
  })

  const s = data?.sections || {}
  const empty = data && !Object.values(s).some((l) => l.length)
  const pick = data?.pick
  const pickProvider = pick?.providers?.find((p) => active.includes(p.id))

  return (
    <div className={`transition-opacity ${isFetching && !isLoading ? 'opacity-70' : ''}`}>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold md:text-3xl">{t('Pour ce soir')}</h1>
          <p className="mt-1 text-sm text-text2">
            {seen !== 'unseen'
              ? t('Uniquement ce que tu peux lancer tout de suite, sur {server} ou tes plateformes.', { server: SERVER_LABELS[status?.media?.server] || 'Plex' })
              : status?.media?.configured
                ? t("Uniquement ce que tu peux lancer tout de suite, sur {server} ou tes plateformes, et que tu n'as pas encore vu.", { server: SERVER_LABELS[status.media.server] })
                : t("Uniquement ce que tu peux lancer tout de suite sur tes plateformes, et que tu n'as pas encore vu.")}
          </p>
          {data?.habit && (
            <p className="mt-1 text-xs text-text3">
              {(() => {
                // Jour de la semaine (0 = lundi) dans la langue de l'interface ; 1er janvier 2024 = un lundi
                const day = new Intl.DateTimeFormat(currentLocale(), { weekday: 'long', timeZone: 'UTC' }).format(new Date(Date.UTC(2024, 0, 1 + data.habit.weekday)))
                return data.habit.prefer === 'tv'
                  ? t('Le {day}, tu regardes plutôt des séries : elles passent devant.', { day })
                  : t('Le {day}, tu regardes plutôt des films : ils passent devant.', { day })
              })()}
            </p>
          )}
        </div>
        <Button
          variant="primary"
          icon={Dices}
          className="shrink-0"
          disabled={!pick}
          onClick={async () => {
            await refetch() // nouveau tirage à chaque fois
            setPickOpen(true)
          }}
        >
          {t('Choisis pour moi')}
        </Button>
      </div>

      <div className="mb-8 space-y-3">
        {(partners?.results?.length > 0 || kidsLabel) ? (
          <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 md:mx-0 md:px-0" role="group" aria-label={t('Pour qui ?')}>
            <button
              type="button"
              onClick={() => setMembers([])}
              aria-pressed={!members.length}
              className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition ${!members.length ? 'border-accent bg-accent/15 text-accent2' : 'border-line text-text2 hover:text-text'}`}
            >
              <User className="h-4 w-4" /> {t('Pour moi')}
            </button>
            {partners?.results?.map((p) => {
              const on = members.includes(p.id)
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => toggleMember(p.id)}
                  aria-pressed={on}
                  className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition ${on ? 'border-accent bg-accent/15 text-accent2' : 'border-line text-text2 hover:text-text'}`}
                >
                  <Users className="h-4 w-4" /> {t('Avec {name}', { name: p.name })}
                </button>
              )
            })}
            {kidsLabel && (
              <button
                type="button"
                onClick={() => setWithKids((k) => !k)}
                aria-pressed={withKids}
                title={kidsLabel}
                className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition ${withKids ? 'border-accent bg-accent/15 text-accent2' : 'border-line text-text2 hover:text-text'}`}
              >
                <Baby className="h-4 w-4" /> {t('Avec les enfants')}
              </button>
            )}
          </div>
        ) : (
          !personal && (
            <p className="text-xs text-text3">
              {t('Soirée à plusieurs : active « Partager mes goûts avec la famille » (Préférences → Partage) et demande à un membre d’en faire autant. Avec des enfants : Préférences → Enfants du foyer.')}
            </p>
          )
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Tabs value={mediaType} onChange={setMediaType} options={MEDIA_OPTIONS} />
          <SeenFilter value={seen} onChange={setSeen} defaultValue="unseen" />
        </div>
        {/* Tri et durée côte à côte (une seule ligne sur téléphone) */}
        <div className="flex gap-2">
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="h-10 min-w-0 flex-1 rounded-xl border border-line bg-bg2 px-3 text-sm outline-none focus:border-accent md:flex-none"
            aria-label={t('Trier par')}
          >
            {TONIGHT_SORTS.map((o) => (
              <option key={o.value} value={o.value}>
                {t('Tri : {label}', { label: t(o.label) })}
              </option>
            ))}
          </select>
          <select
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            className="h-10 min-w-0 flex-1 rounded-xl border border-line bg-bg2 px-3 text-sm outline-none focus:border-accent md:flex-none"
            aria-label={t('Durée')}
          >
            {DURATIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.value ? t('Durée : {label}', { label: t(o.label) }) : t('Toutes les durées')}
              </option>
            ))}
          </select>
        </div>
        <Chips value={mood} onChange={setMood} options={MOODS} />
      </div>

      {error ? (
        <EmptyState title={t('Impossible de préparer ta soirée')} message={error.message} />
      ) : empty ? (
        <EmptyState icon={Popcorn} title={t('Rien ne correspond')} message={t("Élargis la durée ou change d'envie.")} />
      ) : (
        <>
          <MediaRow
            title={members.length > 1 ? t('Dans toutes vos watchlists') : t('Dans vos deux watchlists')}
            subtitle={t('Disponibles ce soir')}
            items={s.together_watchlist?.map((i) => ({ ...i, reason: undefined }))}
            loading={isLoading && members.length > 0}
            renderFooter={footer}
          />
          <MediaRow
            title={members.length > 1 ? t('Pour vous tous') : t('Pour vous deux')}
            subtitle={data?.together_with ? t('D’après tes goûts et ceux de {name}', { name: data.together_with }) : null}
            items={s.together?.map((i) => ({ ...i, why: reasonText(i, t), reason: undefined }))}
            loading={isLoading && members.length > 0}
            renderFooter={(i) => (i.why ? <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-accent2">{i.why}</p> : footer(i))}
          />
          <MediaRow title={t('Reprendre')} subtitle={t('En cours sur ton {server}', { server: SERVER_LABELS[status?.media?.server] || 'Plex' })} items={s.resume} loading={isLoading} renderFooter={footer} />
          <MediaRow title={t('À finir')} subtitle={t('Séries commencées, presque terminées')} items={s.finish} loading={isLoading && seen === 'unseen'} renderFooter={footer} />
          <MediaRow title={t('Ta watchlist, dispo ce soir')} items={s.watchlist} loading={isLoading} renderFooter={footer} />
          <MediaRow title={t('Suggestions dispo ce soir')} subtitle={members.length ? t('Qu’aucun de vous n’a vus') : t("D'après tes goûts")} items={s.suggestions} loading={isLoading} renderFooter={footer} />
          <MediaRow title={t('Pépites de ta bibliothèque')} subtitle={t('Bien notées, pas encore vues')} items={s.library} loading={isLoading} renderFooter={footer} />
          <MediaRow title={t('À revoir')} subtitle={t('Déjà vus, disponibles ce soir')} items={s.rewatch} loading={isLoading && seen !== 'unseen'} renderFooter={footer} />
        </>
      )}

      <Modal open={pickOpen && !!pick} onClose={() => setPickOpen(false)} title={t('Ce soir, on regarde…')}>
        {pick && (
          <div className="flex gap-4">
            <div className="w-28 shrink-0">
              <Poster src={pick.poster} title={pick.title} mediaType={pick.media_type} rounded="rounded-xl" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-lg font-semibold leading-tight">{pick.title}</p>
              <p className="mt-1 text-xs text-text2">{[pick.year, mediaLabel(pick.media_type), pick.runtime && formatRuntime(pick.runtime)].filter(Boolean).join(' · ')}</p>
              <div className="mt-2 flex items-center gap-1.5">
                {pick.in_plex && <PlexBadge server={pick.server} size="sm" />}
                {pick.providers?.filter((p) => active.includes(p.id)).slice(0, 4).map((p) => <PlatformBadge key={p.id} provider={p} size="sm" ring={false} />)}
              </div>
              {pick.overview && <p className="mt-2 line-clamp-3 text-xs text-text2">{pick.overview}</p>}
              <div className="mt-4 flex flex-wrap gap-2">
                {pick.in_plex && pick.plex_url ? (
                  <WatchLink href={pick.plex_url} appRef={{ mediaType: pick.media_type, id: pick.id }}>
                    <Button size="sm" variant="primary" icon={Play} className="!bg-plex !text-black">
                      {t('Lire sur {server}', { server: SERVER_LABELS[pick.server] || 'Plex' })}
                    </Button>
                  </WatchLink>
                ) : (
                  pickProvider && (
                    <Link to={detailPath(pick)} onClick={() => setPickOpen(false)}>
                      <Button size="sm" variant="primary" icon={Play}>
                        {t('Regarder sur {name}', { name: pickProvider.name })}
                      </Button>
                    </Link>
                  )
                )}
                <Link to={detailPath(pick)} onClick={() => setPickOpen(false)}>
                  <Button size="sm" icon={Info}>
                    {t('Fiche')}
                  </Button>
                </Link>
                <Button size="sm" variant="ghost" icon={Dices} onClick={() => refetch()} loading={isFetching}>
                  {t('Autre')}
                </Button>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
