import { useState } from 'react'
import { Star } from 'lucide-react'
import { useT } from '../../i18n'

export default function StarRating({ value = 0, onChange, size = 'md', readOnly = false }) {
  const t = useT()
  const [hover, setHover] = useState(0)
  const px = size === 'lg' ? 'h-9 w-9' : size === 'sm' ? 'h-4 w-4' : 'h-6 w-6'
  const shown = hover || value
  return (
    <div className="inline-flex items-center gap-1" onMouseLeave={() => setHover(0)}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          disabled={readOnly}
          onMouseEnter={() => !readOnly && setHover(n)}
          onClick={() => onChange?.(n)}
          className="transition active:scale-90 disabled:cursor-default"
          aria-label={n > 1 ? t('{n} étoiles', { n }) : t('{n} étoile', { n })}
        >
          <Star className={`${px} ${n <= shown ? 'fill-amber-400 text-amber-400' : 'text-text3'}`} strokeWidth={1.5} />
        </button>
      ))}
    </div>
  )
}
