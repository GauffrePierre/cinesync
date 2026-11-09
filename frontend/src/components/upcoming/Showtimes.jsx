import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { Clapperboard, Clock } from 'lucide-react'
import Poster from '../media/Poster'
import Skeleton from '../ui/Skeleton'
import EmptyState from '../ui/EmptyState'
import { PlexBadge } from '../ui/PlatformBadge'
import { useShowtimes } from '../../hooks/useMedia'
import { formatRuntime, safeUrl } from '../../lib/format'
import { currentLocale, useT } from '../../i18n'

const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
function dayLabel(d, i, t) {
  if (i === 0) return t("Aujourd'hui")
  if (i === 1) return t('Demain')
  const s = new Intl.DateTimeFormat(currentLocale(), { weekday: 'short', day: 'numeric' }).format(d)
  return s.charAt(0).toUpperCase() + s.slice(1)
}

// Films à l'affiche dans tes cinémas, avec les séances (réservation en un clic)
export default function Showtimes({ cinemas }) {
  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => new Date(Date.now() + i * 86400000)), [])
  const [day, setDay] = useState(iso(days[0]))
  const { data, isLoading, error } = useShowtimes(day, cinemas.length > 0)
  const t = useT()

  if (!cinemas.length) {
    return (
      <EmptyState
        icon={Clapperboard}
        title={t('Aucun cinéma suivi')}
        message={t('Choisis tes cinémas dans le Profil pour voir les séances ici.')}
        action={t('Choisir mes cinémas')}
        to="/profile?tab=prefs"
      />
    )
  }

  return (
    <section className="mb-10">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{t("À l'affiche dans tes cinémas")}</h2>
          <p className="text-sm text-text2">{cinemas.map((c) => c.name).join(' · ')}</p>
        </div>
      </div>
      <div className="no-scrollbar -mx-4 mb-5 flex gap-2 overflow-x-auto px-4 md:mx-0 md:px-0">
        {days.map((d, i) => (
          <button
            key={iso(d)}
            onClick={() => setDay(iso(d))}
            className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-medium transition ${
              day === iso(d) ? 'border-accent bg-accent/15 text-accent2' : 'border-line text-text2 hover:text-text'
            }`}
          >
            {dayLabel(d, i, t)}
          </button>
        ))}
      </div>

      {error ? (
        <EmptyState title={t('Séances indisponibles')} message={error.message} />
      ) : isLoading ? (
        <div className="grid gap-3 lg:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-36" />
          ))}
        </div>
      ) : !data?.results.length ? (
        <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-text3">{t('Aucune séance ce jour-là.')}</p>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {data.results.map((f) => (
            <div key={`${f.id}-${f.title}`} className="flex gap-3 rounded-2xl border border-line bg-bg2 p-3">
              {f.id ? (
                <Link to={`/movie/${f.id}`} className="w-20 shrink-0">
                  <Poster src={f.poster} title={f.title} mediaType="movie" rounded="rounded-xl" />
                </Link>
              ) : (
                <div className="w-20 shrink-0">
                  <Poster src={f.poster} title={f.title} mediaType="movie" rounded="rounded-xl" />
                </div>
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-start gap-2">
                  {f.id ? (
                    <Link to={`/movie/${f.id}`} className="min-w-0 flex-1 truncate font-medium hover:text-accent2">
                      {f.title}
                    </Link>
                  ) : (
                    <p className="min-w-0 flex-1 truncate font-medium">{f.title}</p>
                  )}
                  {f.in_plex && <PlexBadge server={f.server} size="xs" />}
                </div>
                <p className="flex items-center gap-2 text-xs text-text2">
                  {f.year}
                  {f.runtime && (
                    <span className="inline-flex items-center gap-1">
                      <Clock className="h-3 w-3" /> {typeof f.runtime === 'number' ? formatRuntime(f.runtime) : f.runtime}
                    </span>
                  )}
                </p>
                {f.cinemas.map((c) => (
                  <div key={c.id} className="mt-2">
                    {cinemas.length > 1 && <p className="mb-1 text-[11px] text-text3">{c.name}</p>}
                    <div className="flex flex-wrap gap-1.5">
                      {c.showtimes.map((s) => {
                        const label = (
                          <>
                            <span className="font-medium">{s.starts_at?.slice(11, 16)}</span>
                            <span className="text-[10px] text-text3">{s.version}</span>
                          </>
                        )
                        const cls = 'inline-flex items-center gap-1 rounded-lg border border-line bg-bg px-2 py-1 text-xs transition'
                        return s.booking_url ? (
                          <a key={s.starts_at + s.version} href={safeUrl(s.booking_url)} target="_blank" rel="noreferrer" className={`${cls} hover:-translate-y-0.5 hover:border-accent`} title={t('Réserver')}>
                            {label}
                          </a>
                        ) : (
                          <span key={s.starts_at + s.version} className={cls}>
                            {label}
                          </span>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
