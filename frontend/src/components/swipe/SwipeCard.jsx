import { Link } from 'react-router'
import { motion, useMotionValue, useTransform } from 'motion/react'
import { Info, Star } from 'lucide-react'
import Poster from '../media/Poster'
import PlatformBadge, { PlexBadge } from '../ui/PlatformBadge'
import { resolveDrag } from '../../hooks/useSwipeGesture'
import { detailPath, mediaLabel } from '../../lib/format'
import { sortProviders } from '../../lib/platforms'
import { useT } from '../../i18n'

const variants = {
  enter: { scale: 0.94, y: 18, opacity: 0 },
  idle: (isTop) => ({ scale: isTop ? 1 : 0.94, y: isTop ? 0 : 18, opacity: 1 }),
  exit: (dir) => ({
    x: (dir?.x || 0) * 650,
    y: (dir?.y || 0) * 750,
    rotate: (dir?.x || 0) * 22,
    opacity: 0,
    transition: { duration: 0.32, ease: 'easeIn' },
  }),
}

// Motif de suggestion envoyé par le serveur (en français) -> traduit
const reasonLabel = (r, t) => {
  const m = r.match(/^Parce que tu as aimé (.+)$/)
  return m ? t('Parce que tu as aimé {title}', { title: m[1] }) : t(r)
}

// Carte plein écran : poster, titre, synopsis court, note, plateformes
export default function SwipeCard({ item, isTop, onSwipe, active = [] }) {
  const x = useMotionValue(0)
  const rotate = useTransform(x, [-300, 300], [-14, 14])
  const likeOpacity = useTransform(x, [30, 120], [0, 1])
  const skipOpacity = useTransform(x, [-120, -30], [1, 0])
  const providers = sortProviders(item.providers, active).slice(0, 5)
  const t = useT()

  return (
    <motion.div
      className="absolute inset-0 touch-none select-none"
      style={{ x, rotate, zIndex: isTop ? 2 : 1 }}
      custom={isTop}
      variants={variants}
      initial="enter"
      animate="idle"
      exit="exit"
      drag={isTop ? 'x' : false}
      dragSnapToOrigin
      dragElastic={0.9}
      onDragEnd={(_, info) => {
        const action = resolveDrag(info)
        if (action) onSwipe(action)
      }}
    >
      <div className="relative h-full w-full overflow-hidden rounded-[28px] bg-bg3 shadow-2xl shadow-black/50">
        <Poster src={item.poster?.replace('/w500/', '/w780/')} title={item.title} mediaType={item.media_type} rounded="rounded-none" className="!aspect-auto h-full" />

        {/* Étiquettes de glissé */}
        <motion.span
          style={{ opacity: likeOpacity }}
          className="absolute left-6 top-8 -rotate-12 rounded-xl border-4 border-emerald-400 px-3 py-1 text-2xl font-semibold text-emerald-400"
        >
          {t("J'AIME")}
        </motion.span>
        <motion.span
          style={{ opacity: skipOpacity }}
          className="absolute right-6 top-8 rotate-12 rounded-xl border-4 border-red-400 px-3 py-1 text-2xl font-semibold text-red-400"
        >
          {t('PASSER')}
        </motion.span>

        <div className="absolute inset-x-0 bottom-0 scrim-card p-5 pt-24 text-white">
          <div className="mb-2 flex items-center gap-2">
            {item.in_plex && <PlexBadge size="sm" />}
            {providers.map((p) => (
              <PlatformBadge key={p.id} provider={p} size="sm" />
            ))}
          </div>
          <div className="flex items-end justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-2xl font-semibold leading-tight">{item.title}</h2>
              <p className="mt-1 flex items-center gap-2 text-sm text-white/75">
                {item.vote_average > 0 && (
                  <span className="inline-flex items-center gap-1">
                    <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" />
                    {Number(item.vote_average).toFixed(1)}
                  </span>
                )}
                <span>{[item.year, mediaLabel(item.media_type)].filter(Boolean).join(' · ')}</span>
              </p>
            </div>
            <Link
              to={detailPath(item)}
              onPointerDown={(e) => e.stopPropagation()}
              className="shrink-0 rounded-full bg-white/15 p-2 backdrop-blur-md hover:bg-white/25"
              aria-label={t('Voir la fiche')}
            >
              <Info className="h-5 w-5" />
            </Link>
          </div>
          {item.reason && <p className="mt-2 text-xs font-medium text-accent2">{reasonLabel(item.reason, t)}</p>}
          {item.overview && <p className="mt-2 line-clamp-3 text-sm text-white/80">{item.overview}</p>}
        </div>
      </div>
    </motion.div>
  )
}
