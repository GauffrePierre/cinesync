import { api } from './api'

// Connexion et comptes (le cookie de session est géré par le navigateur)
export const auth = {
  me: () => api.get('/auth/me'),
  setup: (body) => api.post('/auth/setup', body),
  login: (username, password) => api.post('/auth/login', { username, password }),
  logout: () => api.post('/auth/logout'),
  changePassword: (current_password, new_password) => api.post('/auth/password', { current_password, new_password }),
  updateProfile: (display_name, username) => api.put('/auth/profile', username ? { display_name, username } : { display_name }),
  removePassword: (current_password) => api.del('/auth/password', { current_password }),
  plexPin: (mode = 'link', forwardUrl) => api.post(`/auth/plex/pin?mode=${mode}${forwardUrl ? `&forward_url=${encodeURIComponent(forwardUrl)}` : ''}`),
  plexCheck: (pinId) => api.post(`/auth/plex/pin/${pinId}`),
}
