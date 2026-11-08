import { api } from './api'

// Connexion Trakt uniquement : les données passent par services/library.js (synchronisées avec tous les services)
export const trakt = {
  oauthInfo: () => api.get('/trakt/oauth/info'),
  oauthStart: () => api.get('/trakt/oauth/start'),
  deviceStart: () => api.post('/trakt/device/start'),
  devicePoll: () => api.post('/trakt/device/poll'),
  disconnect: () => api.post('/trakt/disconnect'),
}
