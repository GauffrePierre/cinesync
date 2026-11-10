import { Link } from 'react-router'
import { Clapperboard, Star } from 'lucide-react'
import Poster from './Poster'
import PlatformBadge, { PlexBadge } from '../ui/PlatformBadge'
import PosterActions from './PosterActions'
import { useSettings } from '../../hooks/useMedia'
import { sortProviders } from '../../lib/platforms'
import { detailPath, formatShortDate, mediaLabel } from '../../lib/format'
import { useT } from '../../i18n'
import { reasonText } from '../../lib/reasons'

/**
 * Poster + badges plateformes flottants + titre + méta.
 * fluid : s'adapte à la grille ; sinon largeur fixe (rangées horizontales).
 * meta : 'default' | 'date' (affiche la date de sortie)
 */
export default function MediaCard({ item, fluid = false, meta = 'default', footer }) {
  const t = useT()
  const { data: settings } = useSettings()
  const active = settings?.active_platforms || []
  const providers = sortProviders(item.providers, active)
  const highlighted = active.length ? providers.filter((p) => active.includes(p.id)) : providers
  const shown = (highlighted.length ? highlighted : providers).slice(0, 3)
  const extra = providers.length - shown.length

  const card = (
    <>
      <div className="relative overflow-hidden rounded-2xl shadow-lg shadow-black/20 transition duration-300 group-hover:-translate-y-1 group-hover:shadow-black/40">
        <Poster src={item.poster} title={item.title} mediaType={item.media_type} />
        {item.rank && (
          <span
            className="absolute bottom-10 left-1 select-none text-6xl font-semibold leading-none text-white/90 [-webkit-text-stroke:2px_rgba(0,0,0,0.55)]"
            aria-label={t('Numéro {n} du jour', { n: item.rank })}
          >
            {item.rank}
          </span>
        )}
        <div className="absolute left-2 top-2 flex -space-x-1.5">
          {item.in_plex && <PlexBadge server={item.server} size="xs" />}
          {shown.map((p) => (
            <PlatformBadge key={p.id} provider={p} size="xs" />
          ))}
          {extra > 0 && (
            <span className="inline-flex h-5 items-center rounded-full bg-black/60 px-1.5 text-[9px] font-medium text-white ring-2 ring-black/30">
              +{extra}
            </span>
          )}
        </div>
        <div className="absolute right-2 top-2 flex flex-col items-end gap-1">
          {item.vote_average > 0 && (
            <span className="inline-flex items-center gap-0.5 rounded-lg bg-black/60 px-1.5 py-0.5 text-[10px] font-medium text-white backdrop-blur-md">
              <Star className="h-2.5 w-2.5 fill-amber-400 text-amber-400" />
              {Number(item.vote_average).toFixed(1)}
            </span>
          )}
          {meta === 'date' && item.release_date && (
            <span className="rounded-lg bg-accent px-1.5 py-0.5 text-[10px] font-semibold text-white">{formatShortDate(item.release_date)}</span>
          )}
          {item.in_theaters && (
            <span className="inline-flex items-center gap-1 rounded-lg bg-amber-500 px-1.5 py-0.5 text-[10px] font-semibold text-black" title={t('Au cinéma, pas encore en streaming')}>
              <Clapperboard className="h-2.5 w-2.5" /> {t('Cinéma')}
            </span>
          )}
        </div>
        {item.id && <PosterActions item={item} />}
      </div>
      <div className="mt-2 px-0.5">
        <p className="truncate text-sm font-medium">{item.title}</p>
        <p className="truncate text-xs text-text2">
          {item.trend && (
            <span
              className={`mr-1 font-semibold ${item.trend === 'UP' ? 'text-emerald-500' : item.trend === 'DOWN' ? 'text-red-400' : 'text-text3'}`}
              title={item.trend === 'STABLE' ? t('Stable depuis hier') : t('{n} place(s) depuis hier', { n: `${item.trend_diff > 0 ? '+' : ''}${item.trend_diff}` })}
            >
              {item.trend === 'UP' ? '▲' : item.trend === 'DOWN' ? '▼' : '='}
            </span>
          )}
          {[item.year, mediaLabel(item.media_type), reasonText(item, t)].filter(Boolean).join(' · ')}
        </p>
        {footer}
      </div>
    </>
  )

  const cls = `group block ${fluid ? 'w-full' : 'w-[calc((100vw-3.5rem)/3)] max-w-[132px] shrink-0 sm:w-[132px] md:w-[156px]'}`
  return item.id ? (
    <Link to={detailPath(item)} className={cls}>
      {card}
    </Link>
  ) : (
    <div className={cls}>{card}</div>
  )
}
