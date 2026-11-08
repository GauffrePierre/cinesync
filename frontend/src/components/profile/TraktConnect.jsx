import { Fragment, useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Copy, ExternalLink, Loader2, LogIn, LogOut } from 'lucide-react'
import Button from '../ui/Button'
import { trakt } from '../../services/trakt'
import { safeUrl } from '../../lib/format'
import { useTraktOauth } from '../../hooks/useMedia'
import { toast } from '../../store/uiStore'
import { useT } from '../../i18n'

const DEVICE_ERRORS = {
  expired: 'Le code a expiré, recommence',
  denied: 'Connexion refusée sur Trakt',
  used: 'Ce code a déjà été utilisé, recommence',
  invalid: 'Code invalide, recommence',
}

// Phrase traduite dont les {variables} sont remplacées par des éléments React
const rich = (str, nodes) =>
  str.split(/(\{\w+\})/).map((part, i) => {
    const k = part.match(/^\{(\w+)\}$/)?.[1]
    return k && k in nodes ? <Fragment key={i}>{nodes[k]}</Fragment> : part
  })

/**
 * Connexion Trakt sans client secret.
 * - Par défaut : code d'appareil (tu tapes un code sur auth.trakt.tv/activate), aucune URL de retour.
 * - Alternative : redirection PKCE, qui exige une URL de retour HTTPS déclarée dans l'appli Trakt.
 */
export default function TraktConnect({ settings }) {
  const t = useT()
  const qc = useQueryClient()
  const { data: info } = useTraktOauth()
  const [device, setDevice] = useState(null) // { user_code, verification_url, interval, expires_in }
  const [showRedirect, setShowRedirect] = useState(false)
  const timer = useRef(null)

  useEffect(() => () => clearTimeout(timer.current), [])

  const done = (message, kind) => {
    clearTimeout(timer.current)
    setDevice(null)
    toast(message, kind)
    qc.invalidateQueries()
  }

  const poll = (intervalSec, deadline) => {
    timer.current = setTimeout(async () => {
      if (Date.now() > deadline) return done(t(DEVICE_ERRORS.expired), 'error')
      try {
        const r = await trakt.devicePoll()
        if (r.status === 'connected') return done(r.username ? t('Trakt connecté en tant que {name} !', { name: r.username }) : t('Trakt connecté !'), 'success')
        if (r.status === 'pending') return poll(intervalSec, deadline)
        if (r.status === 'slow_down') return poll(intervalSec + 2, deadline)
        return done(t(DEVICE_ERRORS[r.status] || DEVICE_ERRORS.invalid), 'error')
      } catch (e) {
        done(e.message, 'error')
      }
    }, intervalSec * 1000)
  }

  const startDevice = useMutation({
    mutationFn: trakt.deviceStart,
    onSuccess: (d) => {
      setDevice(d)
      navigator.clipboard?.writeText(d.user_code).catch(() => {})
      poll(d.interval || 5, Date.now() + d.expires_in * 1000)
    },
    onError: (e) => toast(e.message, 'error'),
  })

  const startRedirect = useMutation({
    mutationFn: trakt.oauthStart,
    onSuccess: ({ url }) => (window.location.href = url),
    onError: (e) => toast(e.message, 'error'),
  })

  const disconnect = useMutation({
    mutationFn: trakt.disconnect,
    onSuccess: () => {
      qc.invalidateQueries()
      toast(t('Trakt déconnecté'), 'info')
    },
  })

  const copy = (text, message) => {
    navigator.clipboard?.writeText(text)
    toast(message, 'success')
  }

  const ready = !!settings?.trakt_client_id

  if (settings?.trakt_connected) {
    return (
      <div className="mt-4 flex items-center justify-between gap-3 rounded-xl bg-bg3 px-3 py-2.5">
        <span className="text-sm">
          {rich(t('Connecté en tant que {name}'), { name: <span className="font-medium">{settings.trakt_username || '…'}</span> })}
        </span>
        <Button variant="ghost" size="sm" icon={LogOut} onClick={() => disconnect.mutate()} loading={disconnect.isPending}>
          {t('Déconnecter')}
        </Button>
      </div>
    )
  }

  if (device) {
    return (
      <div className="mt-4 rounded-xl border border-trakt/30 bg-trakt/5 p-4 text-center">
        <p className="text-sm text-text2">{t("Va sur la page d'activation Trakt et saisis ce code :")}</p>
        <button onClick={() => copy(device.user_code, t('Code copié'))} className="mx-auto mt-3 flex items-center gap-2 rounded-xl bg-bg px-4 py-2" title={t('Copier')}>
          <span className="font-mono text-2xl font-semibold tracking-[0.25em]">{device.user_code}</span>
          <Copy className="h-4 w-4 text-text3" />
        </button>
        <a
          href={safeUrl(device.verification_url)}
          target="_blank"
          rel="noreferrer"
          className="mt-4 inline-flex items-center gap-1.5 rounded-xl bg-trakt px-4 py-2 text-sm font-medium text-white hover:brightness-110"
        >
          {t('Ouvrir {url}', { url: device.verification_url.replace('https://', '') })} <ExternalLink className="h-3.5 w-3.5" />
        </a>
        <p className="mt-3 flex items-center justify-center gap-2 text-xs text-text3">
          <Loader2 className="h-3 w-3 animate-spin" /> {t('En attente de ta validation sur Trakt…')}
        </p>
        <button
          onClick={() => {
            clearTimeout(timer.current)
            setDevice(null)
          }}
          className="mt-2 text-xs text-text2 hover:text-text"
        >
          {t('Annuler')}
        </button>
      </div>
    )
  }

  return (
    <div className="mt-4 space-y-3">
      <Button
        variant="primary"
        icon={LogIn}
        className="w-full justify-center !bg-trakt"
        disabled={!ready}
        loading={startDevice.isPending}
        onClick={() => startDevice.mutate()}
      >
        {ready ? t('Se connecter avec Trakt') : t('Enregistre d’abord le client ID')}
      </Button>

      <button onClick={() => setShowRedirect((s) => !s)} className="text-xs text-text2 hover:text-text">
        {showRedirect ? '▾' : '▸'} {t('Autre méthode : redirection (nécessite HTTPS)')}
      </button>
      {showRedirect && (
        <div className="space-y-2 rounded-xl bg-bg3 p-3">
          <span className="block text-xs text-text2">{t('URL de retour à déclarer dans ton application Trakt :')}</span>
          <div className="flex gap-2">
            <code className="flex h-10 min-w-0 flex-1 items-center truncate rounded-lg border border-line bg-bg px-3 text-xs text-text2">
              {info?.redirect_uri || '…'}
            </code>
            <Button size="icon" onClick={() => copy(info?.redirect_uri || '', t('URL copiée'))} aria-label={t('Copier')}>
              <Copy className="h-4 w-4" />
            </Button>
          </div>
          {info && !info.redirect_https && (
            <p className="text-xs text-amber-500">{t("Trakt n'accepte que des URL de retour en HTTPS : utilise le code d'appareil ci-dessus, ou configure PUBLIC_URL en HTTPS.")}</p>
          )}
          <Button size="sm" disabled={!ready || !info?.redirect_https} loading={startRedirect.isPending} onClick={() => startRedirect.mutate()}>
            {t('Se connecter par redirection')}
          </Button>
        </div>
      )}
    </div>
  )
}
