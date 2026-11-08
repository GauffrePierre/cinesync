import { api, qs } from './api'

export const plex = {
  library: (params) => api.get(`/plex/library${qs(params)}`),
  status: (mediaType, id) => api.get(`/plex/status/${mediaType}/${id}`),

  // Connexion via le compte plex.tv
  authPin: (mode = 'link', forwardUrl) => api.post(`/plex/auth/pin${qs({ mode, forward_url: forwardUrl })}`),
  checkPin: (id) => api.post(`/plex/auth/pin/${id}`),
  servers: () => api.get('/plex/servers'),
  selectServer: (machineId) => api.post('/plex/servers/select', { machine_id: machineId }),
  logout: () => api.post('/plex/auth/logout'),
}
