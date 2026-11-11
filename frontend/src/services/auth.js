import { api } from './api'
import { forgetDevice } from './push'

// Connexion et comptes (le cookie de session est géré par le navigateur)
export const auth = {
  me: () => api.get('/auth/me'),
  setup: (body) => api.post('/auth/setup', body),
  login: (username, password) => api.post('/auth/login', { username, password }),
  logout: async () => {
    await forgetDevice()
    // Appareil partagé : les images de la bibliothèque gardées par le service worker partent avec la session
    if (typeof caches !== 'undefined') await caches.delete('plex-images').catch(() => {})
    return api.post('/auth/logout')
  },
  changePassword: (current_password, new_password, code = '') => api.post('/auth/password', { current_password, new_password, code }),
  // Version personnelle en accès libre : fait écrire dans les journaux du serveur le code du premier mot de passe
  protectCode: () => api.post('/auth/protect/code'),
  updateProfile: (display_name, username) => api.put('/auth/profile', username ? { display_name, username } : { display_name }),
  removePassword: (current_password) => api.del('/auth/password', { current_password }),
  plexPin: (mode = 'link') => api.post(`/auth/plex/pin?mode=${mode}`),
  plexCheck: (pinId) => api.post(`/auth/plex/pin/${pinId}`),
  jellyfinLogin: (username, password) => api.post('/auth/jellyfin', { username, password }),
  // Quick Connect : code à valider dans Jellyfin, sans mot de passe
  jellyfinQuickStatus: () => api.get('/auth/jellyfin/quickconnect'),
  jellyfinQuickStart: () => api.post('/auth/jellyfin/quickconnect'),
  jellyfinQuickCheck: (id) => api.post(`/auth/jellyfin/quickconnect/${encodeURIComponent(id)}`),
  // Double authentification : 2e étape de connexion, activation (QR code puis 1er code), désactivation
  loginTwoFactor: (ticket, code) => api.post('/auth/login/2fa', { ticket, code }),
  twoFactorSetup: (password = '') => api.post('/auth/2fa/setup', { password }),
  twoFactorEnable: (code) => api.post('/auth/2fa/enable', { code }),
  twoFactorDisable: (code) => api.post('/auth/2fa/disable', { code }),
  twoFactorRecoveryCodes: (code) => api.post('/auth/2fa/recovery-codes', { code }),
}
