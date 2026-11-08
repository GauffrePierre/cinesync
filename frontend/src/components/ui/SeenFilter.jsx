import { useState } from 'react'
import { Check, ChevronDown, Eye, EyeOff, ListFilter } from 'lucide-react'
import { useUiStore } from '../../store/uiStore'
import { useLibraryKeys } from '../../hooks/useMedia'
import { keyOf } from '../../services/library'
import { useT } from '../../i18n'

const OPTIONS = [
  { value: 'all', label: 'Tous', icon: ListFilter },
  { value: 'unseen', label: 'Pas vus', icon: EyeOff },
  { value: 'seen', label: 'Vus', icon: Eye },
]

// Petit menu à côté de Tout / Films / Séries : tous les titres, seulement ceux pas vus, ou seulement ceux vus.
// Par défaut, choix commun mémorisé ; une page peut avoir le sien (value / onChange) et sa valeur par défaut.
export default function SeenFilter({ value: own, onChange, defaultValue = 'all' }) {
  const t = useT()
  const stored = useUiStore((s) => s.seenFilter)
  const setStored = useUiStore((s) => s.setSeenFilter)
  const value = own ?? stored
  const setValue = onChange ?? setStored
  const [open, setOpen] = useState(false)
  const current = OPTIONS.find((o) => o.value === value) || OPTIONS[0]
  const Icon = current.icon
  const active = current.value !== defaultValue
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('Filtrer : vus ou pas vus')}
        title={t('Filtrer : vus ou pas vus')}
        className={`inline-flex h-[42px] items-center gap-1.5 rounded-xl border px-3 text-sm font-medium transition ${
          active ? 'border-accent/50 bg-accent/10 text-accent2' : 'border-line bg-bg2 text-text2 hover:text-text'
        }`}
      >
        <Icon className="h-4 w-4" />
        {active && <span>{t(current.label)}</span>}
        <ChevronDown className={`h-3.5 w-3.5 transition ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div role="menu" className="absolute right-0 z-20 mt-1 w-44 rounded-xl border border-line bg-bg2 p-1 shadow-xl">
            {OPTIONS.map((o) => (
              <button
                key={o.value}
                role="menuitemradio"
                aria-checked={o.value === value}
                onClick={() => {
                  setValue(o.value)
                  setOpen(false)
                }}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-bg3"
              >
                <o.icon className="h-4 w-4 text-text2" />
                <span className="flex-1">{t(o.label)}</span>
                {o.value === value && <Check className="h-4 w-4 text-accent2" />}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

/** Filtre côté interface (listes déjà chargées, ex. Découvrir), d'après l'état personnel. */
export function useSeenFilterFn() {
  const value = useUiStore((s) => s.seenFilter)
  const { data: keys } = useLibraryKeys()
  if (value === 'all' || !keys) return (items) => items
  const watched = new Set(keys.watched || [])
  return (items) => items?.filter((i) => watched.has(keyOf(i.media_type, i.id)) === (value === 'seen'))
}
