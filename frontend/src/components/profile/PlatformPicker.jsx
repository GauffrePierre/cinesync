import { useMemo, useState } from 'react'
import { Check, Search } from 'lucide-react'
import PlatformBadge from '../ui/PlatformBadge'
import Skeleton from '../ui/Skeleton'
import { useProviderCatalog, useUpdateSettings } from '../../hooks/useMedia'
import { useT } from '../../i18n'

// Sélection multiple des plateformes auxquelles tu es abonné
export default function PlatformPicker({ settings }) {
  const t = useT()
  const { data, isLoading } = useProviderCatalog(settings?.country_code)
  const update = useUpdateSettings()
  const [filter, setFilter] = useState('')
  const [showAll, setShowAll] = useState(false)
  const active = settings?.active_platforms || []

  const providers = useMemo(() => {
    const list = data?.results || []
    const f = filter.toLowerCase()
    const filtered = f ? list.filter((p) => p.name.toLowerCase().includes(f)) : list
    // Actives d'abord, puis par popularité dans le pays
    return [...filtered].sort((a, b) => (active.includes(b.id) ? 1 : 0) - (active.includes(a.id) ? 1 : 0) || a.priority - b.priority)
  }, [data, filter, active])

  const visible = showAll || filter ? providers : providers.slice(0, 18)

  const toggle = (id) => {
    const next = active.includes(id) ? active.filter((p) => p !== id) : [...active, id]
    update.mutate({ active_platforms: next })
  }

  return (
    <div>
      <div className="relative mb-3">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text3" />
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={t('Filtrer les plateformes…')}
          className="h-10 w-full rounded-xl border border-line bg-bg pl-9 pr-3 text-sm outline-none placeholder:text-text3 focus:border-accent"
        />
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {isLoading
          ? Array.from({ length: 9 }).map((_, i) => <Skeleton key={i} className="h-12" />)
          : visible.map((p) => {
              const on = active.includes(p.id)
              return (
                <button
                  key={p.id}
                  onClick={() => toggle(p.id)}
                  className={`flex items-center gap-2.5 rounded-xl border px-3 py-2 text-left text-sm transition ${
                    on ? 'border-accent bg-accent/10' : 'border-line bg-bg hover:border-text3'
                  }`}
                >
                  <PlatformBadge provider={p} size="md" ring={false} />
                  <span className="min-w-0 flex-1 truncate">{p.name}</span>
                  {on && <Check className="h-4 w-4 shrink-0 text-accent2" />}
                </button>
              )
            })}
      </div>
      {!filter && providers.length > 18 && (
        <button onClick={() => setShowAll((s) => !s)} className="mt-3 text-sm text-accent2 hover:underline">
          {showAll ? t('Afficher moins') : t('Afficher les {n} plateformes', { n: providers.length })}
        </button>
      )}
    </div>
  )
}
