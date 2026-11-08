import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Clapperboard, Loader2, Plus, Search, X } from 'lucide-react'
import { user } from '../../services/user'
import { useDebounce } from '../../hooks/useDebounce'
import { useUpdateSettings } from '../../hooks/useMedia'
import { toast } from '../../store/uiStore'
import { useT } from '../../i18n'

// Choix des cinémas suivis (séances dans « À venir » → Sorties cinéma)
const COUNTRY_NAMES = { FR: 'France', DE: 'Allemagne', ES: 'Espagne', TR: 'Turquie', MX: 'Mexique' }

export default function CinemaPicker({ settings }) {
  const t = useT()
  const [q, setQ] = useState('')
  const [country, setCountry] = useState(['FR', 'DE', 'ES', 'TR', 'MX'].includes(settings?.country_code) ? settings.country_code : 'FR')
  const { data: countries } = useQuery({ queryKey: ['cinema-countries'], queryFn: user.cinemaCountries, staleTime: Infinity })
  const debounced = useDebounce(q.trim(), 350)
  const update = useUpdateSettings()
  const selected = settings?.cinemas || []
  const { data, isFetching, error } = useQuery({
    queryKey: ['cinema-search', country, debounced],
    queryFn: () => user.cinemaSearch(debounced, country),
    enabled: debounced.length >= 2,
    staleTime: 3600_000,
  })

  const save = (list, message) => update.mutate({ cinemas: list }, { onSuccess: () => toast(message, 'success') })
  const add = (c) => {
    if (selected.some((s) => s.id === c.id)) return
    save([...selected, c], t('{name} ajouté', { name: c.name }))
    setQ('')
  }
  const remove = (c) => save(selected.filter((s) => s.id !== c.id), t('{name} retiré', { name: c.name }))

  return (
    <div>
      {selected.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {selected.map((c) => (
            <span key={c.id} className="inline-flex items-center gap-2 rounded-full border border-accent/40 bg-accent/10 py-1 pl-3 pr-1 text-sm">
              <Clapperboard className="h-3.5 w-3.5 text-accent2" />
              {c.name}
              {c.city && <span className="text-xs text-text3">{c.city}{c.country && c.country !== 'FR' ? ` · ${c.country}` : ''}</span>}
              <button onClick={() => remove(c)} className="rounded-full p-1 text-text3 hover:bg-bg3 hover:text-text" aria-label={t('Retirer {name}', { name: c.name })}>
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex gap-2">
      <select
        value={country}
        onChange={(e) => setCountry(e.target.value)}
        className="h-10 shrink-0 rounded-xl border border-line bg-bg px-2 text-sm outline-none focus:border-accent"
        aria-label={t('Pays du cinéma')}
      >
        {(countries?.results || [{ code: 'FR', source: 'AlloCiné' }]).map((c) => (
          <option key={c.code} value={c.code}>
            {COUNTRY_NAMES[c.code] ? t(COUNTRY_NAMES[c.code]) : c.code}
          </option>
        ))}
      </select>
      <div className="relative flex-1">
        {isFetching ? (
          <Loader2 className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-text3" />
        ) : (
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text3" />
        )}
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t('Ville ou nom du cinéma (ex. Annecy)…')}
          className="h-10 w-full rounded-xl border border-line bg-bg pl-9 pr-3 text-sm outline-none placeholder:text-text3 focus:border-accent"
        />
      </div>
      </div>
      {debounced.length >= 2 && data && (
        <div className="mt-2 overflow-hidden rounded-xl border border-line">
          {data.results.length === 0 ? (
            <p className="px-3 py-3 text-sm text-text3">{t('Aucun cinéma trouvé pour « {q} ».', { q: debounced })}</p>
          ) : (
            data.results.slice(0, 12).map((c) => {
              const on = selected.some((s) => s.id === c.id)
              return (
                <button
                  key={c.id}
                  onClick={() => add(c)}
                  disabled={on}
                  className="flex w-full items-center gap-3 border-b border-line px-3 py-2 text-left text-sm last:border-none hover:bg-bg3 disabled:opacity-50"
                >
                  <Clapperboard className="h-4 w-4 shrink-0 text-text3" />
                  <span className="min-w-0 flex-1 truncate">{c.name}</span>
                  <span className="text-xs text-text3">
                    {c.zip} {c.city}
                  </span>
                  {!on && <Plus className="h-4 w-4 text-accent2" />}
                </button>
              )
            })
          )}
        </div>
      )}
      {error && <p className="mt-2 text-xs text-red-400">{error.message}</p>}
      <label className="mt-3 flex cursor-pointer items-center justify-between rounded-xl border border-line bg-bg px-3 py-2.5">
        <span className="text-sm">
          {t('Films uniquement')}
          <span className="block text-xs text-text3">{t('Masque opéras, ballets, concerts et spectacles retransmis')}</span>
        </span>
        <input
          type="checkbox"
          checked={settings?.cinema_films_only ?? true}
          onChange={(e) => update.mutate({ cinema_films_only: e.target.checked })}
          className="h-5 w-5 accent-[var(--accent)]"
        />
      </label>
      <p className="mt-2 text-xs text-text3">
        {t(
          'Séances : AlloCiné et ses sites partenaires (source non officielle) — France, Allemagne, Espagne, Turquie, Mexique. Pas encore de source gratuite pour les autres pays (Suisse, Belgique, Italie, Royaume-Uni, États-Unis, Canada, Australie…).',
        )}
      </p>
    </div>
  )
}
