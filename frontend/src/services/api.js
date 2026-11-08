// Wrapper fetch : toutes les requêtes passent par /api (servi par CinéSync lui-même en prod, relayé par Vite en dev)
import { t } from '../i18n'

export class ApiError extends Error {
  constructor(message, status, service) {
    super(message)
    this.status = status
    this.service = service
  }
}

async function request(method, path, body) {
  let res
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(t('Serveur CinéSync injoignable'), 0)
  }
  let data = null
  try {
    data = await res.json()
  } catch {
    /* réponse vide */
  }
  if (!res.ok) {
    // Session expirée ou révoquée : l'écran de connexion reprend la main (voir AuthGate)
    if (res.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('cinesync:unauthorized'))
    const detail = data?.detail
    // Le serveur répond en français : les messages connus sont traduits ici
    const message = typeof detail === 'string' ? t(detail) : Array.isArray(detail) ? t('Données invalides') : t('Erreur {status}', { status: res.status })
    throw new ApiError(message, res.status, data?.service)
  }
  return data
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body = {}) => request('POST', path, body),
  put: (path, body) => request('PUT', path, body),
  patch: (path, body) => request('PATCH', path, body),
  del: (path, body) => request('DELETE', path, body),
}

export function qs(params) {
  const p = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, v)
  })
  const s = p.toString()
  return s ? `?${s}` : ''
}
