import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// Langue du navigateur si elle est proposée (français, anglais, italien, allemand, espagnol), sinon anglais
const SUPPORTED = ['fr', 'en', 'it', 'de', 'es']
const browserLang = () => {
  const code = (typeof navigator !== 'undefined' && navigator.language?.slice(0, 2).toLowerCase()) || 'fr'
  return SUPPORTED.includes(code) ? code : 'en'
}

// Copie locale du thème et de la langue : appliqués avant même la réponse de l'API (pas de flash).
// La source de vérité reste le backend (réglages), synchronisée par useTheme.
export const useSettingsStore = create(
  persist(
    (set) => ({
      theme: 'auto',
      uiLanguage: browserLang(),
      setTheme: (theme) => set({ theme }),
      setUiLanguage: (uiLanguage) => set({ uiLanguage }),
    }),
    { name: 'cinesync-settings' },
  ),
)
