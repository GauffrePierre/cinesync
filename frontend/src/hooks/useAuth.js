import { useQuery, useQueryClient } from '@tanstack/react-query'
import { auth } from '../services/auth'

// Compte connecté : { user, setup_required, plex_login, mode } (user = null si déconnecté)
export const useMe = () => useQuery({ queryKey: ['me'], queryFn: auth.me, staleTime: 5 * 60_000, retry: 1 })

export function useCurrentUser() {
  const { data } = useMe()
  return data?.user || null
}

export const useIsAdmin = () => !!useCurrentUser()?.is_admin

// Version personnelle : une seule personne, ni connexion ni comptes de la famille
export const usePersonal = () => useMe().data?.mode === 'personal'

// Après connexion / déconnexion : les données en cache appartiennent à l'ancien compte.
// La requête ['me'] est mise à jour sur place (la supprimer couperait l'écran qui l'observe).
export function useResetSession() {
  const qc = useQueryClient()
  return (me) => {
    qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'me' })
    if (me) qc.setQueryData(['me'], me)
    else {
      qc.setQueryData(['me'], (old) => (old ? { ...old, user: null } : old))
      qc.invalidateQueries({ queryKey: ['me'] })
    }
  }
}
