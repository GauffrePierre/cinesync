/*
 * Traduction de l'interface.
 * Le texte français sert de clé : t('Découvrir') -> « Discover » en anglais. Une clé absente du
 * dictionnaire s'affiche en français (jamais de trou). Variables : t('{n} titres', { n: 3 }).
 */
import { useCallback } from 'react'
import { useSettingsStore } from '../store/settingsStore'
import en from './en'

const DICTS = { en }

export const UI_LANGUAGES = [
  { code: 'fr', label: 'Français', locale: 'fr-CH' },
  { code: 'en', label: 'English', locale: 'en-GB' },
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
  return useCallback((key, vars) => translate(lang, key, vars), [lang])
}

/** Nombre formaté dans la locale courante. */
export const fmtNumber = (n, opts) => (n == null ? '' : Number(n).toLocaleString(currentLocale(), opts))
