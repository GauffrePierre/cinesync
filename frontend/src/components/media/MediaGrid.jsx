import MediaCard from './MediaCard'
import { CardSkeleton } from '../ui/Skeleton'
import { useLibraryKeys } from '../../hooks/useMedia'

export default function MediaGrid({ items: rawItems = [], loading = false, meta, renderFooter, skeletons = 12, hideDisliked = false }) {
  const { data: keys } = useLibraryKeys()
  const hidden = hideDisliked ? new Set(keys?.disliked || []) : new Set()
  const items = (rawItems || []).filter((i) => !hidden.has(`${i.media_type}:${i.id}`))
  return (
    <div className="grid grid-cols-3 gap-x-3 gap-y-6 sm:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-7">
      {items.map((item) => (
        <MediaCard
          key={`${item.media_type}-${item.id ?? item.rating_key}`}
          item={item}
          fluid
          meta={meta}
          footer={renderFooter?.(item)}
        />
      ))}
      {loading && Array.from({ length: skeletons }).map((_, i) => <CardSkeleton key={`s${i}`} fluid />)}
    </div>
  )
}
