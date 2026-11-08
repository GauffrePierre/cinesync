import { useEffect, useState } from 'react'
import { BellRing, Send, Smartphone } from 'lucide-react'
import Button from '../ui/Button'
import { currentSubscription, push, pushSupported } from '../../services/push'
import { device } from '../../lib/appLinks'
import { toast } from '../../store/uiStore'
import { useT } from '../../i18n'

const standalone = () => window.matchMedia?.('(display-mode: standalone)').matches || window.navigator.standalone === true

// Notifications push sur CET appareil : mêmes alertes que la cloche, même SynCiné fermé
export default function PushSettings() {
  const t = useT()
  const [on, setOn] = useState(null) // null : vérification en cours
  const [busy, setBusy] = useState(false)
  const supported = pushSupported()
  const iosBrowser = device() === 'ios' && !standalone()

  useEffect(() => {
    currentSubscription().then((s) => setOn(!!s), () => setOn(false))
  }, [])

  const toggle = async (value) => {
    setBusy(true)
    try {
      if (value) {
        await push.enable()
        toast(t('Notifications activées sur cet appareil'), 'success')
      } else {
        await push.disable()
      }
      setOn(value)
    } catch (e) {
      toast(Notification.permission === 'denied' ? t('Notifications bloquées : autorise-les dans les réglages du navigateur pour SynCiné') : t(e.message), 'error')
    } finally {
      setBusy(false)
    }
  }

  const test = async () => {
    try {
      await push.test()
    } catch (e) {
      toast(t(e.message), 'error')
    }
  }

  if (iosBrowser || !supported) {
    return (
      <p className="flex items-start gap-2 rounded-xl border border-line bg-bg2 p-3 text-xs text-text2">
        <Smartphone className="mt-0.5 h-4 w-4 shrink-0 text-accent2" />
        {iosBrowser
          ? t('Sur iPhone et iPad, les notifications fonctionnent dans l’app installée : dans Safari, Partager → « Sur l’écran d’accueil », puis ouvre SynCiné depuis son icône.')
          : t('Ce navigateur ne permet pas les notifications push.')}
      </p>
    )
  }

  return (
    <div className="rounded-xl border border-line bg-bg2 px-3 py-3">
      <label className="flex cursor-pointer items-center gap-3">
        <BellRing className="h-5 w-5 shrink-0 text-accent2" />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium">{t('Notifications sur cet appareil')}</span>
          <span className="block text-xs text-text2">{t('Les alertes choisies ci-dessus arrivent aussi sur l’écran, même SynCiné fermé.')}</span>
        </span>
        <input
          type="checkbox"
          checked={!!on}
          disabled={on === null || busy}
          onChange={(e) => toggle(e.target.checked)}
          className="h-5 w-5 shrink-0 accent-[var(--accent)]"
        />
      </label>
      {on && (
        <Button size="sm" variant="ghost" icon={Send} onClick={test} className="mt-2">
          {t('Envoyer une notification d’essai')}
        </Button>
      )}
    </div>
  )
}
