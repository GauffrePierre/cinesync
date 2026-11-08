import { directAppLink, openInApp } from '../../lib/appLinks'
import { safeUrl } from '../../lib/format'

// Lien « Regarder » : sur téléphone et tablette, ouvre l'application (Plex, Netflix…) quand c'est possible
// appRef : { mediaType, id, watchUrl? } — watchUrl : page watch.plex.tv du titre, que l'app Plex ouvre
export default function WatchLink({ href: rawHref, appRef, children, onClick, ...props }) {
  const href = safeUrl(rawHref)
  if (!href) return children ?? null
  // Lien de l'app connu : c'est lui que l'on touche (un vrai lien, condition pour qu'iOS / Android ouvrent l'app)
  const direct = directAppLink(href, appRef)
  if (direct) {
    return (
      <a href={direct} onClick={onClick} {...props}>
        {children}
      </a>
    )
  }
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
