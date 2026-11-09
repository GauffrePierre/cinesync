import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router'
import { AnimatePresence, motion } from 'motion/react'
import { Bookmark, Globe, Loader2, Search, X } from 'lucide-react'
import Poster from '../media/Poster'
import { PlexBadge } from '../ui/PlatformBadge'
import { useGlobalSearch } from '../../hooks/useMedia'
import { useDebounce } from '../../hooks/useDebounce'
import { useUiStore } from '../../store/uiStore'
import { mediaLabel } from '../../lib/format'
import { useT } from '../../i18n'
import { openInApp } from '../../lib/appLinks'

function ResultRow({ item, onSelect }) {
  return (
    <button onClick={() => onSelect(item)} className="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left hover:bg-bg3">
      <div className="w-10 shrink-0">
        <Poster src={item.poster} title={item.title} mediaType={item.media_type} rounded="rounded-lg" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{item.title}</p>
        <p className="truncate text-xs text-text2">{[item.year, mediaLabel(item.media_type), item.section].filter(Boolean).join(' · ')}</p>
      </div>
      {item.in_plex && <PlexBadge server={item.server} size="xs" />}
    </button>
  )
}

function Group({ icon: Icon, title, items, onSelect, color }) {
  if (!items?.length) return null
  return (
    <div className="mb-4">
      <p className="mb-1 flex items-center gap-2 px-2 text-xs font-medium text-text3">
        <Icon className="h-3.5 w-3.5" style={{ color }} />
        {title} <span className="text-text3">· {items.length}</span>
      </p>
      {items.map((item) => (
        <ResultRow key={`${item.media_type}-${item.id ?? item.rating_key}`} item={item} onSelect={onSelect} />
      ))}
    </div>
  )
}

// Recherche globale : TMDB + bibliothèque Plex + watchlist Trakt
export default function SearchOverlay() {
  const t = useT()
  const open = useUiStore((s) => s.searchOpen)
  const setOpen = useUiStore((s) => s.setSearchOpen)
  const [q, setQ] = useState('')
  const debounced = useDebounce(q, 300)
  const { data, isFetching } = useGlobalSearch(debounced)
  const navigate = useNavigate()
  const inputRef = useRef(null)

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50)
    else setQ('')
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, setOpen])

  const select = (item) => {
    setOpen(false)
    if (item.id) navigate(`/${item.media_type}/${item.id}`)
    else if (item.plex_url && !openInApp(item.plex_url)) window.open(item.plex_url, '_blank')
  }

  const hasResults = data && (data.tmdb.length || data.plex.length || data.watchlist.length)

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[60] bg-black/50 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={() => setOpen(false)}
        >
          <motion.div
            className="pt-safe mx-auto flex h-full w-full max-w-2xl flex-col bg-bg2 md:mt-[10vh] md:h-auto md:max-h-[70vh] md:rounded-3xl md:border md:border-line md:shadow-2xl"
            initial={{ y: -16, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -16, opacity: 0 }}
            transition={{ type: 'spring', damping: 28, stiffness: 320 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 border-b border-line px-4 py-3">
              {isFetching ? <Loader2 className="h-5 w-5 animate-spin text-text3" /> : <Search className="h-5 w-5 text-text3" />}
              <input
                ref={inputRef}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={t('Films, séries, ta bibliothèque…')}
                className="h-10 flex-1 bg-transparent text-base outline-none placeholder:text-text3"
              />
              <button onClick={() => setOpen(false)} className="rounded-full p-1.5 text-text2 hover:bg-bg3" aria-label={t('Fermer')}>
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3">
              {debounced.trim().length < 2 ? (
                <p className="px-2 py-8 text-center text-sm text-text3">{t('Tape au moins 2 caractères')}</p>
              ) : !hasResults && !isFetching ? (
                <p className="px-2 py-8 text-center text-sm text-text3">{t('Aucun résultat pour « {q} »', { q: debounced })}</p>
              ) : (
                data && (
                  <>
                    <Group icon={PlexIcon} title={t('Dans ta bibliothèque Plex')} items={data.plex} onSelect={select} color="var(--plex)" />
                    <Group icon={Bookmark} title={t('Dans ta watchlist')} items={data.watchlist} onSelect={select} color="var(--trakt)" />
                    <Group icon={Globe} title="TMDB" items={data.tmdb} onSelect={select} color="#01b4e4" />
                  </>
                )
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  )
}

function PlexIcon(props) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" {...props}>
      <path d="M8 3h5l6 9-6 9H8l6-9z" />
    </svg>
  )
}
