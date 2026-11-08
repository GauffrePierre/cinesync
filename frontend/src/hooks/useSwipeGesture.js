import { useEffect } from 'react'

export const SWIPE_THRESHOLD = 110 // px
export const SWIPE_VELOCITY = 600 // px/s

// Direction de sortie de la carte selon l'action
export const EXIT = {
  skip: { x: -1, y: 0 },
  like: { x: 1, y: 0 },
  watchlist: { x: 0, y: -1 },
  seen: { x: 0, y: 1 },
}

/** Interprète la fin d'un glissé (motion onDragEnd) : 'like' | 'skip' | null */
export function resolveDrag(info) {
  const { offset, velocity } = info
  if (offset.x > SWIPE_THRESHOLD || velocity.x > SWIPE_VELOCITY) return 'like'
  if (offset.x < -SWIPE_THRESHOLD || velocity.x < -SWIPE_VELOCITY) return 'skip'
  return null
}

/** Raccourcis clavier : ← passer, → j'aime, ↑ watchlist, ↓ déjà vu, Retour arrière = annuler */
export function useSwipeKeyboard(handlers, enabled = true) {
  useEffect(() => {
    if (!enabled) return
    const onKey = (e) => {
      if (['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName)) return
      const map = { ArrowLeft: 'skip', ArrowRight: 'like', ArrowUp: 'watchlist', ArrowDown: 'seen', Backspace: 'undo' }
      const action = map[e.key]
      if (action && handlers[action]) {
        e.preventDefault()
        handlers[action]()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [handlers, enabled])
}
