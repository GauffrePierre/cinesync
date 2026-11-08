import { api } from './api'

export const user = {
  settings: () => api.get('/settings'),
  updateSettings: (patch) => api.put('/settings', patch),
  status: () => api.get('/settings/status'),
  test: (service) => api.post(`/settings/test/${service}`),
  stats: () => api.get('/stats'),
  statsActivity: (period, offset, tz) => api.get(`/stats/activity?period=${period}&offset=${offset}&tz=${tz}`),
  statsEvents: (start, end, tz) => api.get(`/stats/events?start=${start}&end=${end}&tz=${tz}`),
  countries: () => api.get('/meta/countries'),
  providers: () => api.get('/meta/providers'),
  cinemaSearch: (q, country) => api.get(`/cinema/search?q=${encodeURIComponent(q)}&country=${country}`),
  cinemaCountries: () => api.get('/cinema/countries'),
  showtimes: (date) => api.get(`/cinema/showtimes${date ? `?date=${date}` : ''}`),
}
