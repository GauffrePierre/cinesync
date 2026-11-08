// Notifications push de SynCiné (chargé par le service worker généré, voir vite.config.js)
// Le contenu est chiffré pour cet appareil par le serveur ; le navigateur le déchiffre avant cet événement.

self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    data = { body: event.data ? event.data.text() : '' }
  }
  const url = typeof data.url === 'string' && data.url.startsWith('/') ? data.url : '/'
  event.waitUntil(
    self.registration.showNotification(data.title || 'SynCiné', {
      body: data.body || '',
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
      tag: data.tag,
      data: { url },
    }),
  )
})

// Toucher la notification : ouvre SynCiné (ou la fenêtre déjà ouverte) sur la bonne page
self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = new URL(event.notification.data?.url || '/', self.location.origin).href
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
      const open = windows.find((w) => w.url.startsWith(self.location.origin))
      if (open) return open.focus().then((w) => (w.navigate ? w.navigate(url).catch(() => w) : w))
      return self.clients.openWindow(url)
    }),
  )
})
