import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { AnimatePresence } from 'motion/react'
import { ChevronLeft, Layers, Loader2, Undo2 } from 'lucide-react'
import SwipeCard from '../components/swipe/SwipeCard'
import SwipeActions from '../components/swipe/SwipeActions'
import RatingModal from '../components/swipe/RatingModal'
import Tabs from '../components/ui/Tabs'
import Toaster from '../components/ui/Toaster'
import { swipe } from '../services/swipe'
import { useSettings } from '../hooks/useMedia'
import { EXIT, useSwipeKeyboard } from '../hooks/useSwipeGesture'
import { toast, useUiStore } from '../store/uiStore'
import { useT } from '../i18n'

const key = (i) => `${i.media_type}-${i.id}`

export default function Swipe() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const filter = useUiStore((s) => s.swipeFilter)
  const setFilter = useUiStore((s) => s.setSwipeFilter)
  const { data: settings } = useSettings()
  const t = useT()

  const [deck, setDeck] = useState([])
  const [history, setHistory] = useState([]) // items swipés (pour annuler)
  const [exitDir, setExitDir] = useState(EXIT.skip)
  const [loading, setLoading] = useState(false)
  const [exhausted, setExhausted] = useState(false)
  const [rating, setRating] = useState(null)
  const fetching = useRef(false)
  const seenKeys = useRef(new Set())

  const loadMore = useCallback(
    async (reset = false) => {
      if (fetching.current) return
      fetching.current = true
      setLoading(true)
      try {
        const res = await swipe.queue(filter, 20)
        const fresh = res.results.filter((i) => !seenKeys.current.has(key(i)))
        fresh.forEach((i) => seenKeys.current.add(key(i)))
        setDeck((d) => (reset ? fresh : [...d, ...fresh]))
        setExhausted(fresh.length === 0)
      } catch (e) {
        toast(e.message, 'error')
      } finally {
        fetching.current = false
        setLoading(false)
      }
    },
    [filter],
  )

  // (Re)chargement quand le filtre change
  useEffect(() => {
    seenKeys.current = new Set()
    setDeck([])
    setExhausted(false)
    loadMore(true)
  }, [filter, loadMore])

  // Préchargement quand il reste peu de cartes
  useEffect(() => {
    if (deck.length > 0 && deck.length < 5 && !exhausted) loadMore()
  }, [deck.length, exhausted, loadMore])

  const current = deck[0]

  const lastCommitted = useRef(null)
  const commit = useCallback(
    async (action, stars) => {
      // Garde contre le double déclenchement (double clic, glissé + clic) sur la même carte
      if (!current || lastCommitted.current === key(current)) return
      lastCommitted.current = key(current)
      setExitDir(EXIT[action])
      setDeck((d) => d.slice(1))
      setHistory((h) => [...h.slice(-19), current])
      try {
        const res = await swipe.act(current, action, stars ?? undefined)
        if (res.message) toast(t(res.message), res.trakt_synced ? 'success' : 'info')
        if (action !== 'skip') {
          qc.invalidateQueries({ queryKey: ['watchlist'] })
          qc.invalidateQueries({ queryKey: ['library-keys'] })
          qc.invalidateQueries({ queryKey: ['suggestions'] })
        }
      } catch (e) {
        toast(e.message, 'error')
      }
    },
    [current, qc],
  )

  const onAction = useCallback(
    (action) => {
      if (!current) return
      if (action === 'seen') setRating(current)
      else commit(action)
    },
    [current, commit],
  )

  const undo = useCallback(async () => {
    const last = history[history.length - 1]
    if (!last) return
    try {
      await swipe.undo()
      lastCommitted.current = null
      setHistory((h) => h.slice(0, -1))
      setExitDir({ x: 0, y: 0 })
      setDeck((d) => [last, ...d])
    } catch (e) {
      toast(e.message, 'error')
    }
  }, [history])

  const handlers = useMemo(
    () => ({
      skip: () => onAction('skip'),
      like: () => onAction('like'),
      watchlist: () => onAction('watchlist'),
      seen: () => onAction('seen'),
      undo,
    }),
    [onAction, undo],
  )
  useSwipeKeyboard(handlers, !rating)

  const visible = deck.slice(0, 2)

  return (
    <div className="pt-safe pb-safe fixed inset-0 flex flex-col overflow-hidden bg-black text-white">
      {/* Fond : backdrop flouté du titre courant */}
      {current?.backdrop || current?.poster ? (
        <img src={current.backdrop || current.poster} alt="" className="absolute inset-0 h-full w-full scale-110 object-cover opacity-40 blur-3xl" />
      ) : null}
      <div className="scrim-swipe absolute inset-0" />

      <header className="relative z-10 flex items-center justify-between gap-2 px-4 py-3">
        <button onClick={() => navigate(-1)} className="rounded-full bg-white/10 p-2 backdrop-blur-md hover:bg-white/20" aria-label={t('Retour')}>
          <ChevronLeft className="h-5 w-5" />
        </button>
        <Tabs
          size="sm"
          value={filter}
          onChange={setFilter}
          className="!border-white/10 !bg-white/10 backdrop-blur-md [&_button]:!text-white/70 [&_button[aria-selected=true]]:!bg-white/20 [&_button[aria-selected=true]]:!text-white"
          options={[
            { value: 'all', label: 'Les deux' },
            { value: 'movie', label: 'Films' },
            { value: 'tv', label: 'Séries' },
          ]}
        />
        <button
          onClick={undo}
          disabled={!history.length}
          className="rounded-full bg-white/10 p-2 backdrop-blur-md hover:bg-white/20 disabled:opacity-30"
          aria-label={t('Annuler le dernier swipe')}
        >
          <Undo2 className="h-5 w-5" />
        </button>
      </header>

      <div className="relative z-10 mx-auto flex w-full max-w-md flex-1 items-center px-4 pb-4">
        <div className="relative aspect-[2/3] max-h-full w-full">
          <AnimatePresence custom={exitDir}>
            {visible
              .map((item, idx) => <SwipeCard key={key(item)} item={item} isTop={idx === 0} onSwipe={onAction} active={settings?.active_platforms} />)
              .reverse()}
          </AnimatePresence>

          {!current && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 rounded-[28px] border border-white/10 bg-white/5 p-8 text-center">
              {loading ? (
                <Loader2 className="h-8 w-8 animate-spin text-white/60" />
              ) : (
                <>
                  <Layers className="h-8 w-8 text-white/50" />
                  <p className="font-medium">{t("Plus rien à proposer pour l'instant")}</p>
                  <p className="text-sm text-white/60">{t('Change de filtre ou reviens plus tard.')}</p>
                  <button onClick={() => loadMore(true)} className="mt-2 rounded-xl bg-white/15 px-4 py-2 text-sm font-medium hover:bg-white/25">
                    {t('Réessayer')}
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="relative z-10 px-4 pb-6">
        <SwipeActions onAction={onAction} disabled={!current} />
        <p className="mt-3 hidden text-center text-xs text-white/40 md:block">{t("Raccourcis : ← passer · → j'aime · ↑ watchlist · ↓ déjà vu · ⌫ annuler")}</p>
      </div>

      <RatingModal
        item={rating}
        onClose={() => setRating(null)}
        onRate={(stars) => {
          setRating(null)
          commit('seen', stars)
        }}
      />
      <Toaster />
    </div>
  )
}
