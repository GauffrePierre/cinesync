import { api } from './api'

// Jellyfin / Emby : serveur (admin) et compte relié de chaque utilisateur
export const jellyfin = {
  connectServer: (body) => api.post('/jellyfin/server', body),
  disconnectServer: () => api.del('/jellyfin/server'),
  users: () => api.get('/jellyfin/users'),
  link: (username, password, currentPassword = '') => api.post('/jellyfin/link', { username, password, current_password: currentPassword }),
  unlink: () => api.del('/jellyfin/link'),
  linkQuickStart: (currentPassword = '') => api.post('/jellyfin/link/quickconnect', { current_password: currentPassword }),
  linkQuickCheck: (id) => api.post(`/jellyfin/link/quickconnect/${encodeURIComponent(id)}`),
}
