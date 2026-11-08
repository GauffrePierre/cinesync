import { api, qs } from './api'

// Actu Ciné : articles et vidéos des sources choisies
export const news = {
  feed: (params = {}) => api.get(`/news${qs(params)}`),
  catalog: () => api.get('/news/catalog'),
  setSources: (sources) => api.put('/news/sources', { sources }),
  addCustom: (url) => api.post('/news/sources/custom', { url }),
}
