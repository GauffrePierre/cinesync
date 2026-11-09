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

// Serveur de la bibliothèque : Plex, Jellyfin ou Emby (couleur et pictogramme de chacun)
export const SERVER_LABELS = { plex: 'Plex', jellyfin: 'Jellyfin', emby: 'Emby' }
const SERVER_STYLE = {
  plex: { cls: 'bg-plex text-black', path: 'M8 3h5l6 9-6 9H8l6-9z' },
  jellyfin: { cls: 'bg-gradient-to-br from-[#aa5cc3] to-[#00a4dc] text-white', path: 'M12 3 3 19h18L12 3zm0 6 4.2 8H7.8L12 9z' },
  emby: { cls: 'bg-[#52b54b] text-white', path: 'M9 6v12l9-6-9-6z' },
}

// Pictogramme du serveur (Plex, Jellyfin ou Emby) dans un rond ou un carré arrondi de sa couleur
export function ServerLogo({ server = 'plex', className = '', title }) {
  const st = SERVER_STYLE[server] || SERVER_STYLE.plex
  return (
    <span className={`inline-flex shrink-0 items-center justify-center font-semibold ${st.cls} ${className}`} title={title}>
      <svg viewBox="0 0 24 24" className="h-1/2 w-1/2" fill="currentColor" aria-hidden="true">
        <path d={st.path} />
      </svg>
    </span>
  )
}

export function PlexBadge({ size = 'sm', className = '', server = 'plex' }) {
  const t = useT()
  return (
    <ServerLogo
      server={server}
      className={`rounded-full ring-2 ring-black/30 ${SIZES[size]} ${className}`}
      title={t('Dans ta bibliothèque {server}', { server: SERVER_LABELS[server] || 'Plex' })}
    />
  )
}
