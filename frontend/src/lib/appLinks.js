// Ouvrir un titre dans l'application installée (Plex, Netflix…) plutôt que dans le navigateur.
//
// - Android : lien « intent » qui vise l'application ; si elle n'est pas installée, Chrome
//   ouvre l'adresse web de secours (browser_fallback_url). Fiable.
// - iPhone / iPad : iOS ne laisse pas une page web choisir l'application. Pour Plex et Netflix,
//   on propose « Ouvrir l'app » (Plex : page watch.plex.tv du titre ; Netflix : nflx://) ou le navigateur,
//   avec un choix mémorisable. Les autres services restent des liens web, qu'iOS ouvre dans
//   l'application quand il le décide (liens universels).
// - Plex (iPhone et Android) : l'app n'ouvre la fiche d'un titre qu'avec son lien watch.plex.tv
//   (liens déclarés par Plex dans watch.plex.tv/.well-known : /movie/… et /show/…). Les liens plex://
//   ouvrent seulement l'accueil. On choisit ensuite son serveur dans l'app.
// - Les liens vers l'app sont de vrais liens touchés (href), jamais une redirection en JavaScript :
//   iOS et Android n'ouvrent une autre application que sur un geste de l'utilisateur.
// - Ordinateur : lien web inchangé.

// Applications Android connues (identifiant du paquet), par domaine du lien
const ANDROID_APPS = [
  ['netflix.com', 'com.netflix.mediaclient'],
  ['disneyplus.com', 'com.disney.disneyplus'],
  ['primevideo.com', 'com.amazon.avod.thirdpartyclient'],
  ['tv.apple.com', 'com.apple.atve.android.appletv'],
  ['canalplus.com', 'com.canal.android.canal'],
  ['max.com', 'com.wbd.stream'],
  ['youtube.com', 'com.google.android.youtube'],
  ['crunchyroll.com', 'com.crunchyroll.crunchyroid'],
  ['arte.tv', 'tv.arte.plus7'],
  ['france.tv', 'fr.francetv.pluzz'],
  ['rakuten.tv', 'tv.wuaki'],
  ['mubi.com', 'com.mubi'],
]
export const PLEX_ANDROID = 'com.plexapp.android'

export function device() {
  if (typeof navigator === 'undefined') return 'desktop'
  const ua = navigator.userAgent || ''
  // iPadOS se présente comme un Mac : on le reconnaît à l'écran tactile
  if (/iPad|iPhone|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return 'ios'
  if (/Android/i.test(ua)) return 'android'
  return 'desktop'
}

function parse(url) {
  try {
    return new URL(url)
  } catch {
    return null
  }
}

const isPlexWeb = (u) => u?.hostname === 'app.plex.tv'

// Lien https ouvert dans l'application Android `pkg` (adresse web de secours si elle n'est pas installée)
export function androidIntentFor(appUrl, pkg, fallback = appUrl) {
  const u = parse(appUrl)
  if (!u) return null
  return `intent://${u.host}${u.pathname}${u.search}#Intent;scheme=https;package=${pkg};S.browser_fallback_url=${encodeURIComponent(fallback)};end`
}

function androidIntent(url, ref) {
  const u = parse(url)
  if (!u) return null
  if (isPlexWeb(u)) return ref?.watchUrl ? androidIntentFor(ref.watchUrl, PLEX_ANDROID, url) : null
  if (u.protocol !== 'https:' || u.hash) return null
  const app = ANDROID_APPS.find(([domain]) => u.hostname === domain || u.hostname.endsWith(`.${domain}`))
  if (!app) return null
  return androidIntentFor(url, app[1])
}

// iOS : l'app Plex n'ouvre la bonne fiche qu'avec un lien watch.plex.tv (les liens plex:// mènent à
// l'accueil) ; on choisit ensuite son serveur. Ce lien dépend du titre : il vient du serveur SynCiné.
function iosApp(url, ref) {
  const u = parse(url)
  if (!u) return null
  if (isPlexWeb(u)) return { app: 'Plex', scheme: ref?.watchUrl || null, ref }
  const netflix = /^\/(?:[a-z]{2}(?:-[a-z]{2})?\/)?title\/(\d+)/i.exec(u.pathname)
  if (u.hostname.endsWith('netflix.com') && netflix) return { app: 'Netflix', scheme: `nflx://www.netflix.com/title/${netflix[1]}` }
  return null
}

// Choix mémorisé sur iOS (par application) : « app » = ouvrir l'app sans demander
const PREF_KEY = 'cinesync-open-in-app'
export function getAppPref(app) {
  try {
    return JSON.parse(localStorage.getItem(PREF_KEY) || '{}')[app] || null
  } catch {
    return null
  }
}
export function setAppPref(app, value) {
  try {
    const prefs = JSON.parse(localStorage.getItem(PREF_KEY) || '{}')
    if (value) prefs[app] = value
    else delete prefs[app]
    localStorage.setItem(PREF_KEY, JSON.stringify(prefs))
  } catch {
    /* stockage indisponible : le choix sera redemandé */
  }
}

/**
 * Lien à mettre directement dans le href (ouverture de l'app au toucher), ou null.
 * Android : intent de l'application. iOS : lien de l'app si « Toujours ouvrir l'app » a été choisi.
 */
export function directAppLink(url, ref) {
  const d = device()
  if (d === 'android') return androidIntent(url, ref)
  if (d === 'ios') {
    const target = iosApp(url, ref)
    if (target?.scheme && getAppPref(target.app) === 'app') return target.scheme
  }
  return null
}

/**
 * Au toucher d'un lien sans lien direct vers l'app : affiche le choix app / navigateur si l'app peut
 * ouvrir ce titre (Plex : son lien watch.plex.tv est alors demandé au serveur SynCiné). Renvoie true
 * si c'est pris en charge (l'appelant annule le lien web), false pour laisser le lien web.
 *
 * iOS demande lui-même « Ouvrir dans … ? » : aucun retour automatique vers le web (il couperait
 * cette question).
 */
export function openInApp(url, ref) {
  const d = device()
  let target = null
  if (d === 'ios') target = iosApp(url, ref)
  else if (d === 'android' && isPlexWeb(parse(url))) target = { app: 'Plex', scheme: null, ref }
  if (!target) return false
  window.dispatchEvent(new CustomEvent('cinesync:open-app', { detail: { ...target, url, android: d === 'android' } }))
  return true
}
