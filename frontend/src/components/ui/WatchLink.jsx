import { openInApp } from '../../lib/appLinks'

// Lien « Regarder » : sur téléphone et tablette, ouvre l'application (Plex, Netflix…) quand c'est possible
// appRef : { mediaType, id, season?, episode?, watchUrl? } — sert à trouver la page du titre dans l'app Plex
export default function WatchLink({ href, appRef, children, onClick, ...props }) {
  if (!href) return children ?? null
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      onClick={(e) => {
        onClick?.(e)
        if (!e.defaultPrevented && openInApp(href, appRef)) e.preventDefault()
      }}
      {...props}
    >
      {children}
    </a>
  )
}
