import { useEffect } from 'react'
import { useSettingsStore } from '../store/settingsStore'
import { useSettings } from './useMedia'

// Applique le thème (<html data-theme>, "auto" = suit le système) et la langue de l'interface (<html lang>)
export function useTheme() {
  const theme = useSettingsStore((s) => s.theme)
  const setTheme = useSettingsStore((s) => s.setTheme)
  const uiLanguage = useSettingsStore((s) => s.uiLanguage)
  const setUiLanguage = useSettingsStore((s) => s.setUiLanguage)
  const { data: settings } = useSettings()

  useEffect(() => {
    if (settings?.theme && settings.theme !== theme) setTheme(settings.theme)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings?.theme])

  useEffect(() => {
    if (settings?.ui_language && settings.ui_language !== uiLanguage) setUiLanguage(settings.ui_language)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings?.ui_language])

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'light' || theme === 'dark') root.dataset.theme = theme
    else delete root.dataset.theme
  }, [theme])

  useEffect(() => {
    document.documentElement.lang = uiLanguage || 'fr'
  }, [uiLanguage])
}
