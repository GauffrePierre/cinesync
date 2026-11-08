// Identité visuelle des plateformes (ids fournisseurs TMDB = packageId JustWatch)
export const PLATFORMS = {
  8: { color: 'var(--netflix)', short: 'N' },
  1796: { color: 'var(--netflix)', short: 'N' },
  337: { color: 'var(--disney)', short: 'D+' },
  119: { color: 'var(--prime)', short: 'P' },
  9: { color: 'var(--prime)', short: 'P' },
  10: { color: 'var(--prime)', short: 'P' },
  350: { color: 'var(--apple)', short: 'tv' },
  2: { color: 'var(--apple)', short: 'tv' },
  381: { color: '#111', short: 'C+' },
  1899: { color: '#002be7', short: 'M' },
  384: { color: '#5822b4', short: 'M' },
  531: { color: '#0064ff', short: 'P+' },
  691: { color: '#e30613', short: 'PS' },
  283: { color: '#f47521', short: 'CR' },
  210: { color: '#0b2a8f', short: 'S' },
}

const FALLBACK = ['#6c63ff', '#14b8a6', '#f97316', '#ec4899', '#22c55e', '#eab308']

export function platformStyle(provider) {
  const known = PLATFORMS[provider.id]
  if (known) return known
  const color = FALLBACK[provider.id % FALLBACK.length]
  const short = (provider.name || '?')
    .split(/\s+/)
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
  return { color, short }
}

// Trie les fournisseurs : plateformes actives d'abord
export function sortProviders(providers = [], active = []) {
  return [...providers].sort((a, b) => (active.includes(b.id) ? 1 : 0) - (active.includes(a.id) ? 1 : 0))
}
