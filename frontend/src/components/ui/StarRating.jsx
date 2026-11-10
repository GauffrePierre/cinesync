import { useState } from 'react'
import { Star } from 'lucide-react'
import { fmtNumber, useT } from '../../i18n'

// Note en étoiles, par demi-étoile : la moitié gauche d'une étoile vaut n - 0,5, la moitié droite n
export default function StarRating({ value = 0, onChange, size = 'md', readOnly = false }) {
  const t = useT()
  const [hover, setHover] = useState(0)
  const px = size === 'lg' ? 'h-9 w-9' : size === 'sm' ? 'h-4 w-4' : 'h-6 w-6'
  const shown = hover || value
  const label = (n) => (n > 1 ? t('{n} étoiles', { n: fmtNumber(n) }) : t('{n} étoile', { n: fmtNumber(n) }))
  return (
    <div className="inline-flex items-center gap-1" onMouseLeave={() => setHover(0)} role="radiogroup" aria-label={t('Ta note')}>
      {[1, 2, 3, 4, 5].map((n) => {
        const fill = shown >= n ? 'full' : shown >= n - 0.5 ? 'half' : 'empty'
        return (
          <span key={n} className="relative inline-flex transition active:scale-90">
            <Star className={`${px} text-text3`} strokeWidth={1.5} />
            {fill !== 'empty' && (
              <Star
                className={`${px} absolute inset-0 fill-amber-400 text-amber-400`}
                style={fill === 'half' ? { clipPath: 'inset(0 50% 0 0)' } : undefined}
                strokeWidth={1.5}
              />
            )}
            {!readOnly &&
              [n - 0.5, n].map((v, i) => (
                <button
                  key={v}
                  type="button"
                  role="radio"
                  aria-checked={value === v}
                  aria-label={label(v)}
                  onMouseEnter={() => setHover(v)}
                  onFocus={() => setHover(v)}
                  onBlur={() => setHover(0)}
                  onClick={() => onChange?.(v)}
                  className={`absolute inset-y-0 w-1/2 ${i ? 'right-0' : 'left-0'} cursor-pointer rounded-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent`}
                />
              ))}
          </span>
        )
      })}
    </div>
  )
}
