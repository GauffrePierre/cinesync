import { useState } from 'react'
import { Check, ChevronDown, Eye, EyeOff, ListFilter } from 'lucide-react'
import { useUiStore } from '../../store/uiStore'
import { useLibraryKeys, useSeenKeys, useSettings } from '../../hooks/useMedia'
import { keyOf } from '../../services/library'
import { useT } from '../../i18n'

/**
 * Filtre vus / pas vus d'un onglet. Chaque onglet a le sien. Par défaut : « Tous », sauf Découvrir quand le
 * réglage « Ne plus proposer les titres déjà vus » est actif (« Pas vus ») ; choisir « Tous » ou « Vus » ne
 * change le réglage que pour cet onglet.
 */
export function usePageSeen(page) {
  const { data: settings } = useSettings()
  const stored = useUiStore((s) => s.seenFilters?.[page])
  const set = useUiStore((s) => s.setSeenFilter)
  const fromSetting = page === 'discover' && !!settings?.hide_seen
  const defaultValue = fromSetting ? 'unseen' : 'all'
  return { value: stored ?? defaultValue, setValue: (v) => set(page, v), defaultValue, fromSetting }
}

const OPTIONS = [
  { value: 'all', label: 'Tous', icon: ListFilter },
  { value: 'unseen', label: 'Pas vus', icon: EyeOff },
  { value: 'seen', label: 'Vus', icon: Eye },
]

// Petit menu à côté de Tout / Films / Séries : tous les titres, seulement ceux pas vus, ou seulement ceux vus.
// Soit l'onglet (page) avec son choix mémorisé, soit une valeur gérée par la page (value / onChange).
export default function SeenFilter({ page, value: own, onChange, defaultValue: ownDefault = 'all' }) {
  const t = useT()
  const pageSeen = usePageSeen(page || 'none')
  const value = own ?? pageSeen.value
  const setValue = onChange ?? pageSeen.setValue
  const defaultValue = page ? pageSeen.defaultValue : ownDefault
  const [open, setOpen] = useState(false)
  const current = OPTIONS.find((o) => o.value === value) || OPTIONS[0]
  const Icon = current.icon
  const active = current.value !== 'all'
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
          <div role="menu" className="absolute right-0 z-20 mt-1 w-56 rounded-xl border border-line bg-bg2 p-1 shadow-xl">
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
            {page && pageSeen.fromSetting && (
              <p className="border-t border-line px-3 py-2 text-[11px] text-text3">
                {value === defaultValue
                  ? t('« Pas vus » d’après ton réglage : choisis Tous ou Vus pour cet onglet seulement.')
                  : t('Réglage « ne plus proposer les vus » ignoré dans cet onglet.')}
              </p>
            )}
          </div>
        </>
      )}
    </div>
  )
}

/**
 * Filtre côté interface (listes déjà chargées, ex. Découvrir). « Pas vus » : films vus et séries à jour
 * retirés (une série avec de nouveaux épisodes reste) ; « Vus » : titres vus ou commencés.
 */
export function useSeenFilterFn(page) {
  const { value } = usePageSeen(page)
  const { data: keys } = useLibraryKeys()
  const smart = useSeenKeys(value === 'unseen')
  if (value === 'all' || !keys) return (items) => items
  const watched = new Set(keys.watched || [])
  if (value === 'seen') return (items) => items?.filter((i) => watched.has(keyOf(i.media_type, i.id)))
  const hidden = smart || watched
  return (items) => items?.filter((i) => !hidden.has(keyOf(i.media_type, i.id)))
}
