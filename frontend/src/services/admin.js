import { api } from './api'

// Espace administrateur : comptes, comptes Plex autorisés, tableau de bord des serveurs (Plex, Jellyfin / Emby)
export const admin = {
  users: () => api.get('/admin/users'),
  createUser: (body) => api.post('/admin/users', body),
  updateUser: (id, patch) => api.patch(`/admin/users/${id}`, patch),
  deleteUser: (id) => api.del(`/admin/users/${id}`),
  plexAccounts: () => api.get('/admin/plex/accounts'),
  allowPlex: (body) => api.post('/admin/plex/accounts', body),
  allowJellyfin: (body) => api.post('/admin/jellyfin/accounts', body),
  // srv = 'plex' ou 'jellyfin' (Jellyfin et Emby)
  servers: () => api.get('/admin/servers'),
  dashboard: (srv) => api.get(`/admin/${srv}/dashboard`),
  scan: (srv, sectionId) => api.post(`/admin/${srv}/scan${sectionId ? `?section_id=${encodeURIComponent(sectionId)}` : ''}`),
  stats: (srv, days = 30) => api.get(`/admin/${srv}/stats?days=${days}`),
  // Sauvegardes de la base
  // Watchlists partagées par la famille (titres hors de leur portée)
  watchlists: () => api.get('/admin/watchlists'),
  backups: () => api.get('/admin/backups'),
  backupNow: () => api.post('/admin/backups'),
  backupSettings: (body) => api.put('/admin/backups/settings', body),
  deleteBackup: (name) => api.del(`/admin/backups/${encodeURIComponent(name)}`),
  backupUrl: (name) => `/api/admin/backups/${encodeURIComponent(name)}`,
}
