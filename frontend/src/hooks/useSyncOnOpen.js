import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { library } from '../services/library'

const KEYS = ['library-keys', 'watchlist', 'media', 'status', 'notifications', 'sync-status', 'suggestions', 'library']
const RESUME_AFTER = 5 * 60_000 // retour dans l'appli après 5 min d'absence
let initialDone = false // une seule synchro au démarrage (StrictMode monte deux fois en dev)

/**
 * Synchronise et actualise les données à l'ouverture de l'appli, puis au retour après une absence
 * (PWA remise au premier plan, onglet réaffiché). Silencieux : aucune attente pour l'utilisateur.
 */
export function useSyncOnOpen() {
  const qc = useQueryClient()

  useEffect(() => {
    const run = async () => {
      try {
        // max_age : le serveur ignore la demande si une synchro date de moins de 2 min
        await library.syncNow(120)
      } catch {
        /* service indisponible : la sidebar et les notifications le signalent déjà */
      }
      KEYS.forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
    }

    if (!initialDone) {
      initialDone = true
      run()
    }

    let hiddenAt = null
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') hiddenAt = Date.now()
      else if (hiddenAt && Date.now() - hiddenAt > RESUME_AFTER) {
        hiddenAt = null
        run()
      }
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [qc])
}
