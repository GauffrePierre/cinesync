import { api } from './api'

export const notifications = {
  list: () => api.get('/notifications'),
  read: (id) => api.post(`/notifications/${id}/read`),
  readAll: () => api.post('/notifications/read-all'),
  remove: (id) => api.del(`/notifications/${id}`),
  checkNow: () => api.post('/notifications/check'),
}
