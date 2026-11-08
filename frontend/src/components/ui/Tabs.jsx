import { useT } from '../../i18n'

// Contrôle segmenté (Films / Séries / Tout, Grille / Calendrier…) — les libellés (en français) sont traduits ici
export default function Tabs({ value, onChange, options, size = 'md', className = '' }) {
  const t = useT()
  const pad = size === 'sm' ? 'px-3 py-1 text-xs' : 'px-4 py-1.5 text-sm'
  return (
    <div className={`inline-flex rounded-xl border border-line bg-bg2 p-1 ${className}`} role="tablist">
      {options.map((o) => {
        const active = o.value === value
        const Icon = o.icon
        return (
          <button
            key={o.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(o.value)}
            className={`inline-flex items-center gap-1.5 rounded-lg font-medium transition ${pad} ${
              active ? 'bg-bg3 text-text shadow-sm' : 'text-text2 hover:text-text'
            }`}
          >
            {Icon && <Icon className="h-4 w-4" />}
            {t(o.label)}
          </button>
        )
      })}
    </div>
  )
}

export const MEDIA_OPTIONS = [
  { value: 'all', label: 'Tout' },
  { value: 'movie', label: 'Films' },
  { value: 'tv', label: 'Séries' },
]
