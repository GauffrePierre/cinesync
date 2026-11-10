// Logo SynCiné : pictogramme (pot de pop-corn) + nom, à droite (barres) ou dessous (écrans de connexion).
// Sources : docs/logo/ ; images générées dans public/icons par dev-tools/make-icons.py
export default function Logo({ stacked = false, className = '' }) {
  if (stacked) {
    return (
      <span className={`inline-flex flex-col items-center gap-2 ${className}`}>
        <img src="/icons/logo-mark.webp" alt="" className="h-24 w-auto" />
        <span role="img" aria-label="SynCiné" className="logo-name h-8" />
      </span>
    )
  }
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <img src="/icons/logo-mark.webp" alt="" className="h-8 w-auto" />
      <span role="img" aria-label="SynCiné" className="logo-name h-[18px]" />
    </span>
  )
}
