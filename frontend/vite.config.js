import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: false, // enregistrement dans src/main.jsx (vérification régulière des mises à jour)
      manifest: false, // on utilise public/manifest.json
      includeAssets: ['icons/*'],
      workbox: {
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/image\.tmdb\.org\/.*/,
            handler: 'CacheFirst',
            options: { cacheName: 'tmdb-images', expiration: { maxEntries: 800, maxAgeSeconds: 30 * 24 * 3600 } },
          },
          {
            urlPattern: /\/api\/plex\/image.*/,
            handler: 'CacheFirst',
            options: { cacheName: 'plex-images', expiration: { maxEntries: 800, maxAgeSeconds: 7 * 24 * 3600 } },
          },
        ],
      },
    }),
  ],
  server: {
    // En dev : le backend tourne sur :8000 (uvicorn), Vite relaie /api
    proxy: { '/api': { target: process.env.VITE_API_TARGET || 'http://localhost:8000' } },
  },
})
