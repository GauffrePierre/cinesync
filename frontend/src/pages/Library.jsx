import { useMemo, useState } from 'react'
import { Library as LibraryIcon, Search } from 'lucide-react'
import MediaGrid from '../components/media/MediaGrid'
import Tabs, { MEDIA_OPTIONS } from '../components/ui/Tabs'
import SeenFilter from '../components/ui/SeenFilter'
import Button from '../components/ui/Button'
import MockBanner from '../components/ui/MockBanner'
import EmptyState from '../components/ui/EmptyState'
import PlatformBadge from '../components/ui/PlatformBadge'
import { useLibrary, useSettings } from '../hooks/useMedia'
import { useDebounce } from '../hooks/useDebounce'
import { useUiStore } from '../store/uiStore'
import { useT } from '../i18n'
import { SORT_OPTIONS } from '../lib/sorts'


export default function Library() {
  const mediaFilter = useUiStore((s) => s.mediaFilter)
  const setMediaFilter = useUiStore((s) => s.setMediaFilter)
  const seenFilter = useUiStore((s) => s.seenFilter)
  const [sort, setSort] = useState('added')
  const [q, setQ] = useState('')
  const [streamingOnly, setStreamingOnly] = useState(false)
  const debouncedQ = useDebounce(q, 300)
  const { data: settings } = useSettings()
  const active = settings?.active_platforms || []
  const t = useT()

  const lib = useLibrary({ mediaType: mediaFilter, sort, q: debouncedQ, seen: seenFilter })
  const pages = lib.data?.pages || []
  const total = pages[0]?.total ?? 0

  const items = useMemo(() => {
    const all = pages.flatMap((p) => p.results)
    if (!streamingOnly) return all
    return all.filter((i) => i.providers?.some((p) => !active.length || active.includes(p.id)))
  }, [pages, streamingOnly, active])

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold md:text-3xl">{t('Bibliothèque')}</h1>
        <p className="mt-1 text-sm text-text2">{lib.isLoading ? t('Chargement…') : total > 1 ? t('{n} titres dans ton Plex', { n: total }) : t('{n} titre dans ton Plex', { n: total })}</p>
      </div>

      <MockBanner service="Plex" show={pages[0]?.mock} />

      <div className="mb-8 flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="flex items-center gap-2">
          <Tabs value={mediaFilter} onChange={setMediaFilter} options={MEDIA_OPTIONS} />
          <SeenFilter />
        </div>
        <div className="relative flex-1 lg:max-w-xs">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text3" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t('Filtrer la bibliothèque…')}
            className="h-10 w-full rounded-xl border border-line bg-bg2 pl-9 pr-3 text-sm outline-none placeholder:text-text3 focus:border-accent"
          />
        </div>
        <div className="flex gap-2">
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="h-10 rounded-xl border border-line bg-bg2 px-3 text-sm outline-none focus:border-accent"
            aria-label={t('Trier par')}
          >
            {SORT_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>
                {t('Tri : {label}', { label: t(s.label) })}
              </option>
            ))}
          </select>
          <button
            onClick={() => setStreamingOnly((s) => !s)}
            className={`h-10 shrink-0 rounded-xl border px-3 text-sm font-medium transition ${
              streamingOnly ? 'border-accent bg-accent/15 text-accent2' : 'border-line bg-bg2 text-text2 hover:text-text'
            }`}
          >
            {t('Aussi en streaming')}
          </button>
        </div>
      </div>

      {lib.error ? (
        <EmptyState title={t('Plex injoignable')} message={lib.error.message} action={t('Vérifier le Profil')} to="/profile" />
      ) : !lib.isLoading && items.length === 0 ? (
        <EmptyState icon={LibraryIcon} title={t('Aucun titre')} message={q ? t('Rien ne correspond à « {q} »', { q }) : t('Ta bibliothèque est vide pour ces filtres.')} />
      ) : (
        <MediaGrid
          items={items}
          loading={lib.isLoading}
          renderFooter={(i) =>
            i.providers?.length > 0 && (
              <div className="mt-1 flex items-center gap-1">
                <span className="text-[10px] text-text3">{t('Aussi sur')}</span>
                <span className="flex -space-x-1">
                  {i.providers.slice(0, 3).map((p) => (
                    <PlatformBadge key={p.id} provider={p} size="xs" ring={false} />
                  ))}
                </span>
              </div>
            )
          }
        />
      )}

      {lib.hasNextPage && (
        <div className="mt-8 flex justify-center">
          <Button onClick={() => lib.fetchNextPage()} loading={lib.isFetchingNextPage}>
            {t('Charger plus')}
          </Button>
        </div>
      )}
    </div>
  )
}
