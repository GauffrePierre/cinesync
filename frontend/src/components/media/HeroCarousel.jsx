import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { AnimatePresence, motion } from 'motion/react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import HeroSection from './HeroSection'
import { useHighlights, useLibraryKeys } from '../../hooks/useMedia'
import { detailPath } from '../../lib/format'
import { useT } from '../../i18n'

const INTERVAL = 7000

// Libellés des diapositives envoyés par le serveur (en français) -> traduits
const SLIDE_PATTERNS = [
  [/^Au cinéma · (.+)$/, 'Au cinéma · {name}'],
  [/^Au cinéma en ce moment \((.+)\)$/, 'Au cinéma en ce moment ({name})'],
  [/^Nouveau sur (?!ton Plex$)(.+)$/, 'Nouveau sur {name}'],
  [/^Parce que tu as aimé (.+)$/, 'Parce que tu as aimé {name}'],
]
function slideLabel(label, t) {
  for (const [re, key] of SLIDE_PATTERNS) {
    const m = label?.match(re)
    if (m) return t(key, { name: m[1] })
  }
  return t(label)
}

/**
 * Grande tuile de Découvrir, à défilement automatique :
 * tendance n°1, au cinéma, nouveau sur Plex / tes plateformes, pour toi.
 * Pause au survol ; flèches, points et glissé du doigt pour naviguer.
 */
export default function HeroCarousel({ fallback, loading }) {
  const { data } = useHighlights()
  const { data: keys } = useLibraryKeys()
  const all = data?.slides?.length ? data.slides : fallback ? [{ label: 'Tendance n°1 cette semaine', item: fallback }] : []
  // Un titre déjà vu ou marqué « pas intéressé » quitte aussitôt le carrousel
  const hidden = new Set([...(keys?.disliked || []), ...(keys?.watched || [])])
  const slides = all.filter((s) => !hidden.has(`${s.item.media_type}:${s.item.id}`))
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)
  const startX = useRef(null)
  const navigate = useNavigate()
  const t = useT()
  const count = slides.length
  const current = slides[Math.min(index, count - 1)]

  useEffect(() => {
    if (paused || count < 2) return
    const t = setInterval(() => setIndex((i) => (i + 1) % count), INTERVAL)
    return () => clearInterval(t)
  }, [paused, count])

  const go = (delta) => setIndex((i) => (i + delta + count) % count)

  if (loading && !current) return <HeroSection loading />
  if (!current) return null

  return (
    <div
      className="relative cursor-pointer"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onPointerDown={(e) => (startX.current = e.clientX)}
      onPointerUp={(e) => {
        if (startX.current == null) return
        const dx = e.clientX - startX.current
        startX.current = null
        if (Math.abs(dx) > 60) return go(dx < 0 ? 1 : -1)
        // Clic sur la tuile (hors boutons et liens) : ouvre la fiche du titre affiché
        if (Math.abs(dx) < 8 && !e.target.closest('button, a')) navigate(detailPath(current.item))
      }}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={`${current.item.media_type}-${current.item.id}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.45 }}
        >
          <HeroSection item={current.item} label={slideLabel(current.label, t)}>
            {count > 1 && (
              <div className="absolute bottom-6 right-4 z-10 flex items-center gap-2 md:bottom-10 md:right-8">
                <button
                  onClick={() => go(-1)}
                  className="hidden rounded-full bg-black/30 p-1.5 text-white backdrop-blur-md transition hover:bg-black/50 md:block"
                  aria-label={t('Précédent')}
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <div className="flex gap-1.5">
                  {slides.map((s, i) => (
                    <button
                      key={`${s.item.media_type}-${s.item.id}`}
                      onClick={() => setIndex(i)}
                      aria-label={t('Diapositive {n} : {label}', { n: i + 1, label: slideLabel(s.label, t) })}
                      className={`h-1.5 rounded-full transition-all ${i === index ? 'w-6 bg-white' : 'w-1.5 bg-white/40 hover:bg-white/70'}`}
                    />
                  ))}
                </div>
                <button
                  onClick={() => go(1)}
                  className="hidden rounded-full bg-black/30 p-1.5 text-white backdrop-blur-md transition hover:bg-black/50 md:block"
                  aria-label={t('Suivant')}
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            )}
          </HeroSection>
        </motion.div>
      </AnimatePresence>
    </div>
  )
}
