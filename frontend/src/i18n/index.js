/*
 * Traduction de l'interface.
 * Le texte français sert de clé : t('Découvrir') -> « Discover » en anglais. Une clé absente du
 * dictionnaire s'affiche en français (jamais de trou). Variables : t('{n} titres', { n: 3 }).
 */
import { useCallback, useEffect, useReducer } from 'react'
import { useSettingsStore } from '../store/settingsStore'
// Dictionnaires chargés à la demande : chacun ne télécharge que sa langue (le français est la clé)
const LOADERS = { en: () => import('./en'), it: () => import('./it'), de: () => import('./de'), es: () => import('./es') }
const DICTS = {}
const listeners = new Set()

/** Charge le dictionnaire d'une langue (une fois) ; les écrans affichés se mettent à jour ensuite. */
export function loadLanguage(lang) {
  if (lang === 'fr' || DICTS[lang] || !LOADERS[lang]) return Promise.resolve()
  return LOADERS[lang]()
    .then((m) => {
      DICTS[lang] = m.default
      listeners.forEach((refresh) => refresh())
    })
    .catch(() => {}) // hors ligne : le français reste affiché
}

export const UI_LANGUAGES = [
  { code: 'fr', label: 'Français', locale: 'fr-CH' },
  { code: 'en', label: 'English', locale: 'en-GB' },
  { code: 'it', label: 'Italiano', locale: 'it-IT' },
  { code: 'de', label: 'Deutsch', locale: 'de-DE' },
  { code: 'es', label: 'Español', locale: 'es-ES' },
]

const format = (str, vars) => (vars ? str.replace(/\{(\w+)\}/g, (m, k) => (vars[k] ?? m)) : str)

export function translate(lang, key, vars) {
  if (key == null) return key
  const dict = DICTS[lang]
  return format((dict && dict[key]) || key, vars)
}

/** Langue courante (hors composant React). */
export const currentLang = () => useSettingsStore.getState().uiLanguage || 'fr'

/** Locale Intl de la langue courante (dates, nombres). */
export const currentLocale = () => (UI_LANGUAGES.find((l) => l.code === currentLang()) || UI_LANGUAGES[0]).locale

/** Traduction hors composant (toasts émis depuis les hooks, utilitaires). */
export const t = (key, vars) => translate(currentLang(), key, vars)

/** Hook de traduction : le composant se re-rend quand la langue change. */
export function useT() {
  const lang = useSettingsStore((s) => s.uiLanguage || 'fr')
  const [loaded, refresh] = useReducer((n) => n + 1, 0)
  useEffect(() => {
    listeners.add(refresh)
    loadLanguage(lang)
    return () => listeners.delete(refresh)
  }, [lang])
  return useCallback((key, vars) => translate(lang, key, vars), [lang, loaded]) // eslint-disable-line react-hooks/exhaustive-deps
}

/** Nombre formaté dans la locale courante. */
export const fmtNumber = (n, opts) => (n == null ? '' : Number(n).toLocaleString(currentLocale(), opts))
