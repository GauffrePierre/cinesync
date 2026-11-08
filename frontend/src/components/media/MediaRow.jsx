import { useRef } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import MediaCard from './MediaCard'
import { CardSkeleton } from '../ui/Skeleton'
import { useLibraryKeys } from '../../hooks/useMedia'
import { useT } from '../../i18n'

// Section à défilement horizontal
export default function MediaRow({ title, subtitle, items: rawItems = [], loading = false, action, meta, empty, renderFooter, hideDisliked = true }) {
  const t = useT()
  const ref = useRef(null)
  const { data: keys } = useLibraryKeys()
  const hidden = hideDisliked ? new Set(keys?.disliked || []) : new Set()
  const items = (rawItems || []).filter((i) => !hidden.has(`${i.media_type}:${i.id}`))
  const scroll = (dir) => ref.current?.scrollBy({ left: dir * ref.current.clientWidth * 0.8, behavior: 'smooth' })

  if (!loading && !items.length && !empty) return null
  return (
    <section className="mb-9">
      <div className="mb-3 flex items-end justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold md:text-xl">{title}</h2>
          {subtitle && <p className="text-sm text-text2">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-1">
          {action}
          <button onClick={() => scroll(-1)} className="hidden rounded-full p-1.5 text-text2 hover:bg-bg3 hover:text-text md:block" aria-label={t('Précédent')}>
            <ChevronLeft className="h-5 w-5" />
          </button>
          <button onClick={() => scroll(1)} className="hidden rounded-full p-1.5 text-text2 hover:bg-bg3 hover:text-text md:block" aria-label={t('Suivant')}>
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>
      </div>
      <div ref={ref} className="no-scrollbar -mx-4 flex snap-x scroll-px-4 gap-3 overflow-x-auto scroll-smooth px-4 pb-2 md:-mx-8 md:scroll-px-8 md:gap-4 md:px-8">
        {loading
          ? Array.from({ length: 8 }).map((_, i) => <CardSkeleton key={i} />)
          : items.length
            ? items.map((item) => (
                <div key={`${item.media_type}-${item.id ?? item.rating_key}`} className="snap-start">
                  <MediaCard item={item} meta={meta} footer={renderFooter?.(item)} />
                </div>
              ))
            : empty}
      </div>
    </section>
  )
}
