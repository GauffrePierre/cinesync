import { api } from './api'

// Jellyfin / Emby : serveur (admin) et compte relié de chaque utilisateur
export const jellyfin = {
  connectServer: (body) => api.post('/jellyfin/server', body),
  disconnectServer: () => api.del('/jellyfin/server'),
  users: () => api.get('/jellyfin/users'),
  link: (username, password) => api.post('/jellyfin/link', { username, password }),
  unlink: () => api.del('/jellyfin/link'),
}
