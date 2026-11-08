import { currentLocale, t } from '../i18n'

const fmt = (opts) => new Intl.DateTimeFormat(currentLocale(), opts)
const parse = (d) => (d ? new Date(d.length === 10 ? `${d}T12:00:00` : d) : null)

export const formatDate = (d) => (d ? fmt({ day: 'numeric', month: 'long', year: 'numeric' }).format(parse(d)) : '')
export const formatShortDate = (d) => (d ? fmt({ day: 'numeric', month: 'short' }).format(parse(d)) : '')
export const formatMonth = (d) => {
  const s = fmt({ month: 'long', year: 'numeric' }).format(d instanceof Date ? d : parse(d))
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export function formatRuntime(min) {
  if (!min) return ''
  const h = Math.floor(min / 60)
  const m = min % 60
  return h ? `${h} h ${String(m).padStart(2, '0')}` : `${m} min` // format court identique en français et en anglais
}

export const mediaLabel = (type) => (type === 'tv' ? t('Série') : t('Film'))

export const detailPath = (item) => `/${item.media_type}/${item.id}`

// Lien venu d'un service extérieur : http(s) seulement (jamais javascript:, data:…)
export const safeUrl = (u) => (typeof u === 'string' && /^https?:\/\//i.test(u.trim()) ? u : undefined)

export function relativeTime(iso) {
  if (!iso) return ''
  // Le serveur stocke ses dates en UTC sans fuseau : sans « Z », le navigateur les lirait en heure locale
  const utc = typeof iso === 'string' && iso.includes('T') && !/(Z|[+-]\d\d:?\d\d)$/.test(iso) ? `${iso}Z` : iso
  const diff = (Date.now() - new Date(utc).getTime()) / 1000
  if (diff < 60) return t("à l'instant")
  if (diff < 3600) return t('il y a {n} min', { n: Math.floor(diff / 60) })
  if (diff < 86400) return t('il y a {n} h', { n: Math.floor(diff / 3600) })
  if (diff < 86400 * 7) return t('il y a {n} j', { n: Math.floor(diff / 86400) })
  return formatShortDate(iso)
}

export const formatMoney = (v) =>
  v ? new Intl.NumberFormat(currentLocale(), { style: 'currency', currency: 'USD', maximumFractionDigits: 0, notation: 'compact' }).format(v) : null
