import { api } from './api'

export const user = {
  settings: () => api.get('/settings'),
  updateSettings: (patch) => api.put('/settings', patch),
  status: () => api.get('/settings/status'),
  test: (service) => api.post(`/settings/test/${service}`),
  stats: () => api.get('/stats'),
  // Premier affichage sans historique : import (POST) puis nouvelle lecture
  statsActivity: async (period, offset, tz) => {
    const url = `/stats/activity?period=${period}&offset=${offset}&tz=${tz}`
    const res = await api.get(url)
    if (!res.needs_import) return res
    await api.post('/stats/import').catch(() => {})
    return api.get(url)
  },
  statsEvents: (start, end, tz) => api.get(`/stats/events?start=${start}&end=${end}&tz=${tz}`),
  countries: () => api.get('/meta/countries'),
  providers: () => api.get('/meta/providers'),
  cinemaSearch: (q, country) => api.get(`/cinema/search?q=${encodeURIComponent(q)}&country=${country}`),
  cinemaCountries: () => api.get('/cinema/countries'),
  showtimes: (date) => api.get(`/cinema/showtimes${date ? `?date=${date}` : ''}`),
}
