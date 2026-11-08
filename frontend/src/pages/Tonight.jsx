import { useState } from 'react'
import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Dices, Info, Play, Popcorn } from 'lucide-react'
import MediaRow from '../components/media/MediaRow'
import Poster from '../components/media/Poster'
import Tabs, { MEDIA_OPTIONS } from '../components/ui/Tabs'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import EmptyState from '../components/ui/EmptyState'
import PlatformBadge, { PlexBadge } from '../components/ui/PlatformBadge'
import { api, qs } from '../services/api'
import { useSettings, useStatus } from '../hooks/useMedia'
import { detailPath, formatRuntime, mediaLabel } from '../lib/format'
import { t as tx, useT } from '../i18n'
import WatchLink from '../components/ui/WatchLink'

const DURATIONS = [
  { value: '', label: 'Peu importe' },
  { value: '90', label: '< 1 h 30' },
  { value: '120', label: '< 2 h' },
  { value: '150', label: '< 2 h 30' },
]
const MOODS = [
  { value: '', label: 'Toutes les envies' },
  { value: 'rire', label: '😄 Rire' },
  { value: 'frissons', label: '😱 Frissons' },
  { value: 'action', label: '💥 Action' },
  { value: 'evasion', label: '🚀 Évasion' },
  { value: 'emotion', label: '🥲 Émotion' },
  { value: 'famille', label: '👨‍👩‍👧 Famille' },
  { value: 'comprendre', label: '🧠 Comprendre' },
]

function Chips({ value, onChange, options }) {
  const t = useT()
  return (
    <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 md:mx-0 md:px-0">
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
  )
}

const footer = (i) =>
  i.resume ? (
    <div className="mt-1">
      <p className="truncate text-[11px] text-text2">{tx(i.resume)}</p>
      {i.progress != null && (
        <div className="mt-1 h-1 overflow-hidden rounded-full bg-bg3">
          <div className="h-full rounded-full bg-plex" style={{ width: `${i.progress}%` }} />
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
  const [pickOpen, setPickOpen] = useState(false)
  const { data: settings } = useSettings()
  const active = settings?.active_platforms || []
  const t = useT()
  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ['tonight', mediaType, duration, mood],
    queryFn: () => api.get(`/tonight${qs({ media_type: mediaType, max_runtime: duration, mood })}`),
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
            {status?.plex?.configured
              ? t("Uniquement ce que tu peux lancer tout de suite, sur Plex ou tes plateformes, et que tu n'as pas encore vu.")
              : t("Uniquement ce que tu peux lancer tout de suite sur tes plateformes, et que tu n'as pas encore vu.")}
          </p>
        </div>
        <Button
          variant="primary"
          icon={Dices}
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
        <Tabs value={mediaType} onChange={setMediaType} options={MEDIA_OPTIONS} />
        <Chips value={duration} onChange={setDuration} options={DURATIONS} />
        <Chips value={mood} onChange={setMood} options={MOODS} />
      </div>

      {error ? (
        <EmptyState title={t('Impossible de préparer ta soirée')} message={error.message} />
      ) : empty ? (
        <EmptyState icon={Popcorn} title={t('Rien ne correspond')} message={t("Élargis la durée ou change d'envie.")} />
      ) : (
        <>
          <MediaRow title={t('Reprendre')} subtitle={t('En cours sur ton Plex')} items={s.resume} loading={isLoading} renderFooter={footer} />
          <MediaRow title={t('Ta watchlist, dispo ce soir')} items={s.watchlist} loading={isLoading} renderFooter={footer} />
          <MediaRow title={t('Suggestions dispo ce soir')} subtitle={t("D'après tes goûts")} items={s.suggestions} loading={isLoading} renderFooter={footer} />
          <MediaRow title={t('Pépites de ta bibliothèque')} subtitle={t('Bien notées, pas encore vues')} items={s.library} loading={isLoading} renderFooter={footer} />
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
                {pick.in_plex && <PlexBadge size="sm" />}
                {pick.providers?.filter((p) => active.includes(p.id)).slice(0, 4).map((p) => <PlatformBadge key={p.id} provider={p} size="sm" ring={false} />)}
              </div>
              {pick.overview && <p className="mt-2 line-clamp-3 text-xs text-text2">{pick.overview}</p>}
              <div className="mt-4 flex flex-wrap gap-2">
                {pick.in_plex && pick.plex_url ? (
                  <WatchLink href={pick.plex_url} appRef={{ mediaType: pick.media_type, id: pick.id }}>
                    <Button size="sm" variant="primary" icon={Play} className="!bg-plex !text-black">
                      {t('Lire sur Plex')}
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
