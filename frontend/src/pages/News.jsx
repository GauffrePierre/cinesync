import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Check, ExternalLink, Newspaper, Play, Plus, Settings2, Trash2, Youtube } from 'lucide-react'
import Tabs from '../components/ui/Tabs'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import EmptyState from '../components/ui/EmptyState'
import Skeleton from '../components/ui/Skeleton'
import WatchLink from '../components/ui/WatchLink'
import { news } from '../services/news'
import { user as userApi } from '../services/user'
import { useIsServerAdmin } from '../hooks/useAuth'
import { relativeTime } from '../lib/format'
import { toast } from '../store/uiStore'
import { useT } from '../i18n'

const KINDS = [
  { value: 'all', label: 'Tout' },
  { value: 'article', label: 'Articles' },
  { value: 'video', label: 'Vidéos' },
]

// Visuel de remplacement : couleur stable par source
function Placeholder({ name, video }) {
  const hue = [...(name || '?')].reduce((a, c) => a + c.charCodeAt(0), 0) % 360
  return (
    <div className="flex h-full w-full items-center justify-center" style={{ background: `linear-gradient(135deg, hsl(${hue} 40% 26%), hsl(${(hue + 40) % 360} 45% 14%))` }}>
      {video ? <Play className="h-8 w-8 text-white/60" /> : <Newspaper className="h-8 w-8 text-white/50" />}
    </div>
  )
}

function Card({ item, featured = false }) {
  const [broken, setBroken] = useState(false)
  const video = item.kind === 'video'
  return (
    <WatchLink
      href={item.url}
      className={`group flex overflow-hidden rounded-2xl border border-line bg-bg2 transition hover:-translate-y-0.5 hover:border-text3 ${
        featured ? 'flex-col md:col-span-2 md:flex-row' : 'flex-col'
      }`}
    >
      <div className={`relative shrink-0 overflow-hidden bg-bg3 ${featured ? 'aspect-video md:aspect-auto md:w-3/5' : 'aspect-video'}`}>
        {item.image && !broken ? (
          <img src={item.image} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setBroken(true)} className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]" />
        ) : (
          <Placeholder name={item.source_name} video={video} />
        )}
        {video && (
          <span className="absolute bottom-2 left-2 inline-flex items-center gap-1 rounded-md bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-white">
            <Youtube className="h-3 w-3" /> YouTube
          </span>
        )}
      </div>
      <div className={`flex min-w-0 flex-1 flex-col ${featured ? 'p-5 md:p-6' : 'p-4'}`}>
        <p className="mb-1.5 flex items-center gap-2 text-[11px] text-text3">
          <span className="truncate font-medium text-accent2">{item.source_name}</span>
          {item.published && <span className="shrink-0">· {relativeTime(item.published)}</span>}
        </p>
        <h2 className={`font-semibold leading-snug ${featured ? 'text-xl md:text-2xl' : 'line-clamp-3 text-[15px]'}`}>{item.title}</h2>
        {item.summary && <p className={`mt-2 text-sm text-text2 ${featured ? 'line-clamp-4' : 'line-clamp-2'}`}>{item.summary}</p>}
      </div>
    </WatchLink>
  )
}

function Toggle({ on, onChange, label, sub }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!on)}
      aria-pressed={on}
      className={`flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition ${on ? 'border-accent/50 bg-accent/10' : 'border-line bg-bg hover:border-text3'}`}
    >
      <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border ${on ? 'border-accent bg-accent text-white' : 'border-line'}`}>
        {on && <Check className="h-3.5 w-3.5" />}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium">{label}</span>
        {sub && <span className="block truncate text-[11px] text-text3">{sub}</span>}
      </span>
    </button>
  )
}

function SourcesModal({ open, onClose }) {
  const t = useT()
  const qc = useQueryClient()
  const isAdmin = useIsServerAdmin()
  const [url, setUrl] = useState('')
  const [ytKey, setYtKey] = useState('')
  const { data } = useQuery({ queryKey: ['news-catalog'], queryFn: news.catalog, enabled: open })
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['news-catalog'] })
    qc.invalidateQueries({ queryKey: ['news'] })
  }
  const save = useMutation({ mutationFn: news.setSources, onSuccess: refresh, onError: (e) => toast(e.message, 'error') })
  const add = useMutation({
    mutationFn: news.addCustom,
    onSuccess: (r) => {
      toast(t('« {name} » ajouté', { name: r.source.name }), 'success')
      setUrl('')
      refresh()
    },
    onError: (e) => toast(e.message, 'error'),
  })
  const saveKey = useMutation({
    mutationFn: () => userApi.updateSettings({ youtube_api_key: ytKey }),
    onSuccess: () => {
      toast(t('Clé API YouTube enregistrée'), 'success')
      setYtKey('')
      refresh()
    },
    onError: (e) => toast(e.message, 'error'),
  })

  const active = data?.active || []
  const ids = new Set(active.map((s) => s.id))
  const custom = active.filter((s) => s.id.startsWith('rss:') || s.id.startsWith('yt:'))
  const set = (next) => save.mutate(next.map((s) => ({ id: s.id })))
  const toggle = (id, on) => set(on ? [...active, { id }] : active.filter((s) => s.id !== id))
  const groups = [
    ['fr', t('Sites en français')],
    ['en', t('Sites en anglais')],
  ]

  return (
    <Modal open={open} onClose={onClose} title={t('Sources de l’Actu Ciné')} className="max-h-[88dvh] overflow-y-auto sm:max-w-lg">
      {!data ? (
        <Skeleton className="h-40" />
      ) : (
        <div className="space-y-5">
          {groups.map(([lang, title]) => (
            <section key={lang}>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-text3">{title}</h3>
              <div className="grid gap-2 sm:grid-cols-2">
                {data.catalog
                  .filter((s) => s.lang === lang)
                  .map((s) => (
                    <Toggle key={s.id} on={ids.has(s.id)} onChange={(on) => toggle(s.id, on)} label={s.name} sub={s.home?.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')} />
                  ))}
              </div>
            </section>
          ))}

          <section>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-text3">{t('Mes sources')}</h3>
            {custom.length > 0 && (
              <ul className="mb-3 space-y-2">
                {custom.map((s) => (
                  <li key={s.id} className="flex items-center gap-3 rounded-xl border border-line bg-bg px-3 py-2">
                    {s.kind === 'youtube' ? <Youtube className="h-4 w-4 shrink-0 text-red-500" /> : <Newspaper className="h-4 w-4 shrink-0 text-text3" />}
                    <span className="min-w-0 flex-1 truncate text-sm">{s.name}</span>
                    <button onClick={() => set(active.filter((x) => x.id !== s.id))} className="rounded-lg p-1.5 text-text3 hover:bg-bg3 hover:text-red-400" aria-label={t('Retirer')}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                if (url.trim()) add.mutate(url.trim())
              }}
            >
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder={t('Site, flux RSS ou chaîne YouTube')}
                aria-label={t('Site, flux RSS ou chaîne YouTube')}
                className="h-10 min-w-0 flex-1 rounded-xl border border-line bg-bg px-3 text-sm outline-none placeholder:text-text3 focus:border-accent"
              />
              <Button type="submit" variant="primary" icon={Plus} loading={add.isPending}>
                {t('Ajouter')}
              </Button>
            </form>
            <p className="mt-2 text-[11px] text-text3">{t('Exemples : critikat.com, youtube.com/@chaine. SynCiné trouve le flux tout seul.')}</p>
          </section>

          <p className="rounded-xl bg-bg3/60 p-3 text-xs text-text2">
            {t('Les articles s’ouvrent sur le site d’origine : si tu as un compte ou un abonnement (Écran Large, Le Monde…), connecte-toi sur le site dans ton navigateur pour tout lire.')}
          </p>

          {isAdmin && (
            <section>
              <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-text3">{t('Clé API YouTube (admin, facultatif)')}</h3>
              <p className="mb-2 text-[11px] text-text3">
                {data.youtube_api
                  ? t('Clé enregistrée. Elle sert de secours quand YouTube ne fournit pas le flux d’une chaîne.')
                  : t('Secours quand YouTube ne fournit pas le flux d’une chaîne. Clé gratuite : Google Cloud Console → YouTube Data API v3.')}
              </p>
              <form
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault()
                  saveKey.mutate()
                }}
              >
                <input
                  value={ytKey}
                  onChange={(e) => setYtKey(e.target.value)}
                  type="password"
                  autoComplete="off"
                  placeholder={data.youtube_api ? '••••••••' : 'AIza…'}
                  aria-label={t('Clé API YouTube (admin, facultatif)')}
                  className="h-10 min-w-0 flex-1 rounded-xl border border-line bg-bg px-3 text-sm outline-none focus:border-accent"
                />
                <Button type="submit" loading={saveKey.isPending} disabled={!ytKey.trim()}>
                  {t('Enregistrer')}
                </Button>
              </form>
            </section>
          )}
        </div>
      )}
    </Modal>
  )
}

// Actu Ciné : articles des sites de cinéma et vidéos YouTube, les plus récents d'abord
export default function News() {
  const t = useT()
  const [kind, setKind] = useState('all')
  const [source, setSource] = useState(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const { data, isLoading, error } = useQuery({ queryKey: ['news', kind], queryFn: () => news.feed({ kind }), staleTime: 10 * 60_000 })

  const sources = data?.sources || []
  const items = useMemo(() => (data?.results || []).filter((i) => !source || i.source === source), [data, source])
  const failing = sources.filter((s) => s.error)

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold md:text-3xl">{t('Actu Ciné')}</h1>
          <p className="mt-1 text-sm text-text2">{t('Les dernières critiques, actus et vidéos de tes sources préférées.')}</p>
        </div>
        <Button icon={Settings2} onClick={() => setSettingsOpen(true)}>
          {t('Sources')}
        </Button>
      </div>

      <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-center">
        <Tabs value={kind} onChange={setKind} options={KINDS} />
        {sources.length > 1 && (
          <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 md:mx-0 md:px-0">
            <button
              onClick={() => setSource(null)}
              className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-medium ${!source ? 'border-accent bg-accent/15 text-accent2' : 'border-line text-text2 hover:text-text'}`}
            >
              {t('Toutes')}
            </button>
            {sources.map((s) => (
              <button
                key={s.id}
                onClick={() => setSource(source === s.id ? null : s.id)}
                title={s.error || undefined}
                className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-3 py-1.5 text-xs font-medium ${
                  source === s.id ? 'border-accent bg-accent/15 text-accent2' : 'border-line text-text2 hover:text-text'
                } ${s.error ? 'opacity-60' : ''}`}
              >
                {s.kind === 'youtube' && <Youtube className="h-3 w-3" />}
                {s.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {failing.length > 0 && (
        <p className="mb-4 flex items-center gap-2 text-xs text-text3">
          <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
          {t('Indisponible pour le moment : {names}', { names: failing.map((s) => s.name).join(', ') })}
        </p>
      )}

      {error ? (
        <EmptyState icon={Newspaper} title={t('Actu Ciné indisponible')} message={error.message} />
      ) : isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="aspect-[4/3] rounded-2xl" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState icon={Newspaper} title={t('Rien à lire pour le moment')} message={t('Ajoute des sources pour remplir ton fil.')} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((it, i) => (
            <Card key={it.id} item={it} featured={i === 0 && !source} />
          ))}
        </div>
      )}

      <p className="mt-8 flex items-center justify-center gap-1 text-[11px] text-text3">
        <ExternalLink className="h-3 w-3" /> {t('Chaque article s’ouvre sur le site de sa source.')}
      </p>

      <SourcesModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  )
}
