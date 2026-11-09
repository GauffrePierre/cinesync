import { useState } from 'react'
import { ChevronDown, ExternalLink } from 'lucide-react'
import PlatformBadge, { PlexBadge } from '../../ui/PlatformBadge'
import { useT } from '../../../i18n'
import WatchLink from '../../ui/WatchLink'

const cardCls = (highlight, clickable) =>
  `flex items-center gap-3 rounded-xl border px-3 py-2.5 transition ${highlight} ${clickable ? 'hover:border-text3' : ''}`

function Tile({ href, appRef, icon, name, sub, highlight = 'border-line bg-bg2' }) {
  const content = (
    <>
      {icon}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{name}</p>
        <p className="truncate text-[11px] text-text3">{sub || ' '}</p>
      </div>
      {href && <ExternalLink className="h-4 w-4 shrink-0 text-text3" />}
    </>
  )
  return href ? (
    <WatchLink href={href} appRef={appRef} className={cardCls(highlight, true)}>
      {content}
    </WatchLink>
  ) : (
    <div className={cardCls(highlight, false)}>{content}</div>
  )
}

function ProviderTile({ p, fallback, active }) {
  const t = useT()
  const mine = active.includes(p.id)
  return (
    <Tile
      href={p.url || fallback}
      icon={<PlatformBadge provider={p} size="md" ring={false} />}
      name={p.name}
      sub={[mine && t('Ton abonnement'), p.quality, p.url ? t('Lien direct') : null].filter(Boolean).join(' · ')}
      highlight={mine ? 'border-accent/40 bg-accent/5' : 'border-line bg-bg2'}
    />
  )
}

const GRID = 'grid gap-2 sm:grid-cols-2 lg:grid-cols-3'

// Location / achat : repliés par défaut (ils prennent beaucoup de place)
function Collapsible({ title, items, fallback, active }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  if (!items?.length) return null
  return (
    <div className="rounded-xl border border-line">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-3 px-3 py-2.5 text-left" aria-expanded={open}>
        <span className="text-sm font-medium">{title}</span>
        <span className="flex -space-x-1.5">
          {items.slice(0, 6).map((p) => (
            <PlatformBadge key={p.id} provider={p} size="xs" />
          ))}
        </span>
        <span className="text-xs text-text3">{items.length > 1 ? t('{n} options', { n: items.length }) : t('{n} option', { n: items.length })}</span>
        <ChevronDown className={`ml-auto h-4 w-4 text-text3 transition ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className={`${GRID} border-t border-line p-2`}>
          {items.map((p) => (
            <ProviderTile key={`${p.id}-${p.type}`} p={p} fallback={fallback} active={active} />
          ))}
        </div>
      )}
    </div>
  )
}

// Où regarder : Plex en premier, puis le streaming ; location et achat repliés
export default function Availability({ data, active = [] }) {
  const t = useT()
  const a = data.availability || {}
  const stream = [...(a.stream || [])].sort((x, y) => (active.includes(y.id) ? 1 : 0) - (active.includes(x.id) ? 1 : 0))
  const inPlex = data.plex?.available
  const nothing = !stream.length && !a.rent?.length && !a.buy?.length && !inPlex

  return (
    <section className="mb-10">
      <h2 className="mb-1 text-lg font-semibold">{t('Où regarder')}</h2>
      <p className="mb-4 text-xs text-text3">
        {a.source === 'tmdb+justwatch'
          ? t('En {country} · données JustWatch (liens directs)', { country: data.country })
          : t('En {country} · données JustWatch via TMDB', { country: data.country })}
      </p>

      {nothing ? (
        <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-text3">{t('Pas disponible en streaming dans ton pays pour le moment.')}</p>
      ) : (
        <div className="space-y-3">
          {(inPlex || stream.length > 0) && (
            <div className={GRID}>
              {inPlex && (
                <Tile
                  href={data.plex.url || undefined}
                  appRef={{ mediaType: data.media_type, id: data.id, watchUrl: data.plex.watch_url }}
                  icon={<PlexBadge size="md" server={data.plex?.server} />}
                  name="Plex"
                  sub={t('Dans ta bibliothèque · lire maintenant')}
                  highlight="border-plex/50 bg-plex/10"
                />
              )}
              {stream.map((p) => (
                <ProviderTile key={`${p.id}-${p.type}`} p={p} fallback={a.link} active={active} />
              ))}
            </div>
          )}
          <Collapsible title={t('Location')} items={a.rent} fallback={a.link} active={active} />
          <Collapsible title={t('Achat')} items={a.buy} fallback={a.link} active={active} />
        </div>
      )}
    </section>
  )
}
