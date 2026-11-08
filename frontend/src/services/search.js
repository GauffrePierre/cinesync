import { api, qs } from './api'

export const search = {
  global: (q) => api.get(`/search${qs({ q })}`),
}
