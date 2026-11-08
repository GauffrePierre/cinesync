import { api } from './api'

// Demandes d'ajout à Plex (envoyées à Seerr si connecté, sinon en attente pour l'administrateur)
export const requests = {
  list: (scope = 'mine') => api.get(`/requests${scope === 'all' ? '?scope=all' : ''}`),
  create: (item) =>
    api.post('/requests', {
      tmdb_id: Number(item.id),
      media_type: item.media_type,
      title: item.title,
      year: item.year,
      poster: item.poster_small || item.poster,
    }),
  sendToSeerr: (id) => api.post(`/requests/${id}/send`),
  setStatus: (id, status) => api.patch(`/requests/${id}`, { status }),
  remove: (id) => api.del(`/requests/${id}`),
}

export const REQUEST_STATUS = {
  pending: { label: 'En attente', cls: 'bg-amber-500/15 text-amber-500' },
  sent: { label: 'Envoyée à Seerr', cls: 'bg-seerr/15 text-seerr' },
  declined: { label: 'Refusée', cls: 'bg-red-500/15 text-red-400' },
  available: { label: 'Disponible', cls: 'bg-emerald-500/15 text-emerald-500' },
}
