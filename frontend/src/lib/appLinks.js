// Ouvrir un titre dans l'application installée (Plex, Netflix…) plutôt que dans le navigateur.
//
// - Android : lien « intent » qui vise l'application ; si elle n'est pas installée, Chrome
//   ouvre l'adresse web de secours (browser_fallback_url). Fiable.
// - iPhone / iPad : iOS ne laisse pas une page web choisir l'application. Pour Plex et Netflix,
//   on propose « Ouvrir l'app » (Plex : page watch.plex.tv du titre ; Netflix : nflx://) ou le navigateur,
//   avec un choix mémorisable. Les autres services restent des liens web, qu'iOS ouvre dans
//   l'application quand il le décide (liens universels).
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
const PLEX_ANDROID = 'com.plexapp.android'

export function device() {
  if (typeof navigator === 'undefined') return 'desktop'
  const ua = navigator.userAgent || ''
  // iPadOS se présente comme un Mac : on le reconnaît à l'écran tactile
  if (/iPad|iPhone|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return 'ios'
  if (/Android/i.test(ua)) return 'android'
  return 'desktop'
}

// Lien web Plex (app.plex.tv/desktop/#!/server/<id>/details?key=/library/metadata/<n>) -> lien de l'application
export function plexAppLink(webUrl) {
  const m = /\/server\/([^/]+)\/details\?key=([^&]+)/.exec(webUrl || '')
  if (!m) return null
  return `plex://preplay/?metadataKey=${encodeURIComponent(decodeURIComponent(m[2]))}&server=${m[1]}`
}

function androidIntent(url) {
  let u
  try {
    u = new URL(url)
  } catch {
    return null
  }
  const plex = u.hostname === 'app.plex.tv' ? plexAppLink(url) : null
  if (plex) {
    const p = new URL(plex)
    return `intent://${p.host}${p.pathname}${p.search}#Intent;scheme=plex;package=${PLEX_ANDROID};S.browser_fallback_url=${encodeURIComponent(url)};end`
  }
  if (u.protocol !== 'https:' || u.hash) return null
  const app = ANDROID_APPS.find(([domain]) => u.hostname === domain || u.hostname.endsWith(`.${domain}`))
  if (!app) return null
  return `intent://${u.host}${u.pathname}${u.search}#Intent;scheme=https;package=${app[1]};S.browser_fallback_url=${encodeURIComponent(url)};end`
}

// iOS : l'app Plex n'ouvre la bonne fiche qu'avec un lien watch.plex.tv (les liens plex:// mènent à
// l'accueil) ; on choisit ensuite son serveur. Ce lien dépend du titre : il vient du serveur CinéSync.
function iosApp(url, ref) {
  let u
  try {
    u = new URL(url)
  } catch {
    return null
  }
  if (u.hostname === 'app.plex.tv') return { app: 'Plex', scheme: ref?.watchUrl || null, ref }
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
 * Ouvre `url` dans l'application si possible. Renvoie true si l'ouverture est prise en charge
 * (l'appelant annule alors le comportement normal du lien), false pour laisser le lien web.
 *
 * iOS demande lui-même « Ouvrir dans … ? » : aucun retour automatique vers le web (il couperait
 * cette question). On propose plutôt le choix app / navigateur (composant AppChooser).
 */
export function openInApp(url, ref) {
  const d = device()
  if (d === 'android') {
    const intent = androidIntent(url)
    if (!intent) return false
    window.location.href = intent
    return true
  }
  if (d === 'ios') {
    const target = iosApp(url, ref)
    if (!target) return false
    if (target.scheme && getAppPref(target.app) === 'app') {
      window.location.href = target.scheme
    } else {
      window.dispatchEvent(new CustomEvent('cinesync:open-app', { detail: { ...target, url } }))
    }
    return true
  }
  return false
}
