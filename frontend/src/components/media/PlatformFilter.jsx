import PlatformBadge from '../ui/PlatformBadge'
import { useProviderCatalog, useSettings } from '../../hooks/useMedia'
import { useUiStore } from '../../store/uiStore'
import { useT } from '../../i18n'

// Puces de filtre par plateforme (uniquement les plateformes actives du profil)
export default function PlatformFilter() {
  const { data: settings } = useSettings()
  const { data: catalog } = useProviderCatalog(settings?.country_code)
  const selected = useUiStore((s) => s.platformFilter)
  const toggle = useUiStore((s) => s.togglePlatform)
  const clear = useUiStore((s) => s.clearPlatforms)
  const t = useT()

  const active = settings?.active_platforms || []
  if (!active.length) return null
  const providers = active.map((id) => catalog?.results?.find((p) => p.id === id) || { id, name: `#${id}` })

  return (
    <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 md:mx-0 md:px-0">
      <button
        onClick={clear}
        className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-medium transition ${
          selected.length === 0 ? 'border-accent bg-accent/15 text-accent2' : 'border-line text-text2 hover:text-text'
        }`}
      >
        {t('Toutes')}
      </button>
      {providers.map((p) => {
        const on = selected.includes(p.id)
        return (
          <button
            key={p.id}
            onClick={() => toggle(p.id)}
            className={`flex shrink-0 items-center gap-1.5 rounded-full border py-1 pl-1 pr-3 text-xs font-medium transition ${
              on ? 'border-accent bg-accent/15 text-text' : 'border-line text-text2 hover:text-text'
            }`}
          >
            <PlatformBadge provider={p} size="xs" ring={false} />
            {p.name}
          </button>
        )
      })}
    </div>
  )
}

// Filtre réutilisable : type de média + plateformes sélectionnées
export function useMediaFilters() {
  const mediaFilter = useUiStore((s) => s.mediaFilter)
  const platformFilter = useUiStore((s) => s.platformFilter)
  return (items = []) =>
    items.filter(
      (i) =>
        (mediaFilter === 'all' || i.media_type === mediaFilter) &&
        (platformFilter.length === 0 || i.providers?.some((p) => platformFilter.includes(p.id))),
    )
}
