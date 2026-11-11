import { api } from './api'

// Notifications push sur cet appareil (Web Push). iPhone / iPad : seulement dans la PWA installée.

export const pushSupported = () => typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window

const toKey = (b64) => {
  const raw = atob((b64 + '='.repeat((4 - (b64.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(raw, (c) => c.charCodeAt(0))
}

async function registration() {
  return navigator.serviceWorker.ready
}

export async function currentSubscription() {
  if (!pushSupported()) return null
  const reg = await navigator.serviceWorker.getRegistration()
  return reg ? reg.pushManager.getSubscription() : null
}

export const push = {
  config: () => api.get('/push/config'),

  async enable() {
    const permission = await Notification.requestPermission()
    if (permission !== 'granted') throw new Error('Notifications refusées')
    const { public_key: key } = await api.get('/push/config')
    const reg = await registration()
    let sub = await reg.pushManager.getSubscription()
    if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: toKey(key) })
    const json = sub.toJSON()
    await api.post('/push/subscribe', { endpoint: json.endpoint, keys: json.keys })
    return sub
  },

  async disable() {
    const sub = await currentSubscription()
    if (!sub) return
    await api.post('/push/unsubscribe', { endpoint: sub.endpoint }).catch(() => {})
    await sub.unsubscribe().catch(() => {})
  },

  async test() {
    const sub = await currentSubscription()
    if (!sub) throw new Error("Cet appareil n'est pas abonné")
    return api.post('/push/test', { endpoint: sub.endpoint })
  },
}

// Ouverture de l'appli : l'appareil déjà abonné dans ce navigateur se réinscrit auprès du serveur, qui oublie les
// appareils d'un compte quand ses sessions sont fermées (changement de mot de passe, compte désactivé)
export async function resyncDevice() {
  try {
    if (!pushSupported() || Notification.permission !== 'granted') return
    const sub = await currentSubscription()
    if (!sub) return
    const json = sub.toJSON()
    await api.post('/push/subscribe', { endpoint: json.endpoint, keys: json.keys })
  } catch {
    /* rien à faire : les notifications se réactivent depuis le profil */
  }
}

// Déconnexion : cet appareil ne doit plus recevoir les notifications du compte qui s'en va
export async function forgetDevice() {
  try {
    await push.disable()
  } catch {
    /* rien à faire */
  }
}
