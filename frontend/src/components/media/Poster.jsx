import { useState } from 'react'
import { Film, Tv } from 'lucide-react'

// Affiche avec visuel de remplacement (dégradé + titre) si l'image manque
export default function Poster({ src, title, mediaType, className = '', rounded = 'rounded-2xl' }) {
  const [broken, setBroken] = useState(false)
  if (src && !broken) {
    return (
      <img
        src={src}
        alt={title}
        loading="lazy"
        onError={() => setBroken(true)}
        className={`aspect-[2/3] w-full bg-bg3 object-cover ${rounded} ${className}`}
      />
    )
  }
  const Icon = mediaType === 'tv' ? Tv : Film
  const hue = [...(title || '?')].reduce((a, c) => a + c.charCodeAt(0), 0) % 360
  return (
    <div
      className={`flex aspect-[2/3] w-full flex-col items-center justify-center gap-3 p-3 text-center ${rounded} ${className}`}
      style={{ background: `linear-gradient(160deg, hsl(${hue} 45% 30%), hsl(${(hue + 50) % 360} 50% 14%))` }}
    >
      <Icon className="h-7 w-7 text-white/50" strokeWidth={1.5} />
      <span className="line-clamp-3 text-sm font-medium text-white/90">{title}</span>
    </div>
  )
}
