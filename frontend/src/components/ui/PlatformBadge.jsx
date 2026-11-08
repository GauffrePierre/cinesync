import { useState } from 'react'
import { platformStyle } from '../../lib/platforms'
import { useT } from '../../i18n'

const SIZES = { xs: 'h-5 w-5 text-[8px]', sm: 'h-6 w-6 text-[9px]', md: 'h-8 w-8 text-[11px]', lg: 'h-11 w-11 text-sm' }

// Rond coloré : logo de la plateforme, ou initiale sur sa couleur
export default function PlatformBadge({ provider, size = 'sm', className = '', ring = true }) {
  const [broken, setBroken] = useState(false)
  const { color, short } = platformStyle(provider)
  const base = `inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full font-semibold text-white ${SIZES[size]} ${
    ring ? 'ring-2 ring-black/30' : ''
  } ${className}`

  if (provider.logo && !broken) {
    return (
      <span className={base} title={provider.name} style={{ background: color }}>
        <img src={provider.logo} alt={provider.name} className="h-full w-full object-cover" loading="lazy" onError={() => setBroken(true)} />
      </span>
    )
  }
  return (
    <span className={base} title={provider.name} style={{ background: color }}>
      {short}
    </span>
  )
}

export function PlexBadge({ size = 'sm', className = '' }) {
  const t = useT()
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full bg-plex font-semibold text-black ring-2 ring-black/30 ${SIZES[size]} ${className}`}
      title={t('Dans ta bibliothèque Plex')}
    >
      <svg viewBox="0 0 24 24" className="h-1/2 w-1/2" fill="currentColor" aria-hidden="true">
        <path d="M8 3h5l6 9-6 9H8l6-9z" />
      </svg>
    </span>
  )
}
