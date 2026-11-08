import { api, qs } from './api'

export const swipe = {
  queue: (mediaType = 'all', count = 20) => api.get(`/swipe/queue${qs({ media_type: mediaType, count })}`),
  act: (item, action, rating) =>
    api.post('/swipe', { tmdb_id: item.id, media_type: item.media_type, action, rating, title: item.title }),
  undo: () => api.post('/swipe/undo'),
  stats: () => api.get('/swipe/stats'),
  reset: (action) => api.del(`/swipe/history${action ? `?action=${action}` : ''}`),
}
