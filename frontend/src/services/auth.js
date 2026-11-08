import { api } from './api'
import { forgetDevice } from './push'

// Connexion et comptes (le cookie de session est géré par le navigateur)
export const auth = {
  me: () => api.get('/auth/me'),
  setup: (body) => api.post('/auth/setup', body),
  login: (username, password) => api.post('/auth/login', { username, password }),
  logout: async () => {
    await forgetDevice()
    return api.post('/auth/logout')
  },
  changePassword: (current_password, new_password) => api.post('/auth/password', { current_password, new_password }),
  updateProfile: (display_name, username) => api.put('/auth/profile', username ? { display_name, username } : { display_name }),
  removePassword: (current_password) => api.del('/auth/password', { current_password }),
  plexPin: (mode = 'link') => api.post(`/auth/plex/pin?mode=${mode}`),
  plexCheck: (pinId) => api.post(`/auth/plex/pin/${pinId}`),
  // Double authentification : 2e étape de connexion, activation (QR code puis 1er code), désactivation
  loginTwoFactor: (ticket, code) => api.post('/auth/login/2fa', { ticket, code }),
  twoFactorSetup: (password = '') => api.post('/auth/2fa/setup', { password }),
  twoFactorEnable: (code) => api.post('/auth/2fa/enable', { code }),
  twoFactorDisable: (code) => api.post('/auth/2fa/disable', { code }),
  twoFactorRecoveryCodes: (code) => api.post('/auth/2fa/recovery-codes', { code }),
}
