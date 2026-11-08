import { api, qs } from './api'

// État personnel fusionné (Trakt + Plex + Letterboxd + CinéSync) et actions synchronisées
const ref = (mediaType, id, title) => ({ media_type: mediaType, tmdb_id: Number(id), title: title || '' })

export const library = {
  keys: () => api.get('/library/keys'),
  watchlist: (params) => api.get(`/library/watchlist${qs(params)}`),
  state: (mediaType, id) => api.get(`/library/state/${mediaType}/${id}`),

  addToWatchlist: (mediaType, id, title) => api.post('/library/watchlist', ref(mediaType, id, title)),
  removeFromWatchlist: (mediaType, id) => api.del(`/library/watchlist/${mediaType}/${id}`),
  markWatched: (mediaType, id, title) => api.post('/library/watched', ref(mediaType, id, title)),
  rate: (mediaType, id, stars, title) => api.post('/library/rating', { ...ref(mediaType, id, title), rating: stars }),
  like: (mediaType, id, title) => api.post('/library/like', ref(mediaType, id, title)),
  unwatch: (mediaType, id) => api.del(`/library/watched/${mediaType}/${id}`),
  unlike: (mediaType, id) => api.del(`/library/like/${mediaType}/${id}`),
  dislike: (mediaType, id, title) => api.post('/library/dislike', ref(mediaType, id, title)),
  undislike: (mediaType, id) => api.del(`/library/dislike/${mediaType}/${id}`),
  disliked: () => api.get('/library/disliked'),

  syncStatus: () => api.get('/library/sync'),
  syncNow: (maxAge) => api.post(`/library/sync${maxAge ? `?max_age=${maxAge}` : ''}`),
  syncPreview: () => api.get('/library/sync/preview'),
}

export const keyOf = (mediaType, id) => `${mediaType}:${id}`

export const SOURCE_LABELS = { trakt: 'Trakt', plex: 'Plex', letterboxd: 'Letterboxd', local: 'CinéSync' }
