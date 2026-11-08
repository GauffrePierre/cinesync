import { api, qs } from './api'

export const tmdb = {
  trending: (mediaType = 'all', page = 1) => api.get(`/tmdb/trending${qs({ media_type: mediaType, page })}`),
  upcoming: (mediaType = 'all', page = 1, kind = 'all') => api.get(`/tmdb/upcoming${qs({ media_type: mediaType, page, kind })}`),
  detail: (mediaType, id) => api.get(`/tmdb/${mediaType}/${id}`),
  providers: (mediaType, id) => api.get(`/tmdb/${mediaType}/${id}/providers`),
  collection: (id) => api.get(`/tmdb/collection/${id}`),
  genres: () => api.get('/tmdb/genres'),
}

// Vues agrégées
export const media = {
  full: (mediaType, id) => api.get(`/media/${mediaType}/${id}`),
  highlights: () => api.get('/media/highlights'),
  suggestions: (mediaType = 'all', limit = 20) => api.get(`/media/suggestions${qs({ media_type: mediaType, limit })}`),
}

export const justwatch = {
  newOnPlatforms: (days = 7) => api.get(`/justwatch/new${qs({ days })}`),
  charts: (mediaType) => api.get(`/justwatch/charts${qs({ media_type: mediaType })}`),
}
