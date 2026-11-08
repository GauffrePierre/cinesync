import { create } from 'zustand'
import { persist } from 'zustand/middleware'

const browserLang = () => (typeof navigator !== 'undefined' && !navigator.language?.startsWith('fr') ? 'en' : 'fr')

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
