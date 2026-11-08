import { api } from './api'

// Espace administrateur : comptes, comptes Plex autorisés, tableau de bord du serveur Plex
export const admin = {
  users: () => api.get('/admin/users'),
  createUser: (body) => api.post('/admin/users', body),
  updateUser: (id, patch) => api.patch(`/admin/users/${id}`, patch),
  deleteUser: (id) => api.del(`/admin/users/${id}`),
  plexAccounts: () => api.get('/admin/plex/accounts'),
  allowPlex: (body) => api.post('/admin/plex/accounts', body),
  dashboard: () => api.get('/admin/plex/dashboard'),
  scan: (sectionId) => api.post(`/admin/plex/scan${sectionId ? `?section_id=${encodeURIComponent(sectionId)}` : ''}`),
  stats: (days = 30) => api.get(`/admin/plex/stats?days=${days}`),
}
