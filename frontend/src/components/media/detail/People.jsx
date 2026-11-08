import { User } from 'lucide-react'
import { useT } from '../../../i18n'

function Avatar({ src, name, size = 'h-20 w-20' }) {
  return src ? (
    <img src={src} alt={name} loading="lazy" className={`${size} rounded-full bg-bg3 object-cover`} />
  ) : (
    <span className={`${size} flex items-center justify-center rounded-full bg-bg3 text-text3`}>
      <User className="h-1/3 w-1/3" />
    </span>
  )
}

// Casting principal : photo, nom, personnage
export function Cast({ cast = [] }) {
  const t = useT()
  if (!cast.length) return null
  return (
    <section className="mb-10">
      <h2 className="mb-4 text-lg font-semibold">{t('Casting')}</h2>
      <div className="no-scrollbar -mx-4 flex gap-4 overflow-x-auto px-4 md:-mx-8 md:px-8">
        {cast.map((c) => (
          <div key={`${c.id}-${c.character}`} className="w-20 shrink-0 text-center md:w-24">
            <Avatar src={c.photo} name={c.name} size="h-20 w-20 md:h-24 md:w-24 mx-auto" />
            <p className="mt-2 line-clamp-2 text-xs font-medium">{c.name}</p>
            {c.character && <p className="line-clamp-2 text-[11px] text-text3">{c.character}</p>}
          </div>
        ))}
      </div>
    </section>
  )
}

const ROLES = [
  ['creators', 'Création'],
  ['directors', 'Réalisation'],
  ['writers', 'Scénario'],
  ['composers', 'Musique'],
  ['cinematographers', 'Photographie'],
  ['producers', 'Production'],
]

// Équipe technique
export function Crew({ crew }) {
  const t = useT()
  const groups = ROLES.filter(([k]) => crew?.[k]?.length)
  if (!groups.length) return null
  return (
    <section className="mb-10">
      <h2 className="mb-4 text-lg font-semibold">{t('Équipe technique')}</h2>
      <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
        {groups.map(([k, label]) => (
          <div key={k}>
            <p className="mb-1 text-xs text-text3">{t(label)}</p>
            {crew[k].map((p) => (
              <p key={p.id} className="text-sm font-medium">
                {p.name}
              </p>
            ))}
          </div>
        ))}
      </div>
    </section>
  )
}
