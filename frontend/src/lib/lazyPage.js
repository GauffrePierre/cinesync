import { lazy } from 'react'

// Page chargée à la demande. Après une mise à jour du serveur, un ancien onglet peut réclamer un fichier qui
// n'existe plus : on recharge alors l'appli une seule fois (repère en sessionStorage) plutôt que d'afficher une erreur.
const KEY = 'syncine.chunkReload'

export default function lazyPage(load) {
  return lazy(() =>
    load()
      .then((mod) => {
        try {
          sessionStorage.removeItem(KEY)
        } catch {
          /* stockage indisponible */
        }
        return mod
      })
      .catch((err) => {
        let reloaded = false
        try {
          reloaded = sessionStorage.getItem(KEY) === '1'
          if (!reloaded) sessionStorage.setItem(KEY, '1')
        } catch {
          reloaded = true // sans stockage, pas de rechargement en boucle possible : on laisse l'erreur
        }
        if (!reloaded) {
          window.location.reload()
          return new Promise(() => {}) // le rechargement prend le relais
        }
        throw err
      }),
  )
}
