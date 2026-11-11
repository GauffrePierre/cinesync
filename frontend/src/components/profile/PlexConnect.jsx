import { Fragment, useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Copy, ExternalLink, Loader2, LogIn, LogOut, RefreshCw, Server, WifiOff } from 'lucide-react'
import Button from '../ui/Button'
import { plex } from '../../services/plex'
import { copyText } from '../../lib/clipboard'
import { toast } from '../../store/uiStore'
import { useT } from '../../i18n'

const KIND_LABEL = { local: 'réseau local', remote: 'accès distant', relay: 'relais Plex (débit limité)' }

// Phrase traduite dont les {variables} sont remplacées par des éléments React
const rich = (str, nodes) =>
  str.split(/(\{\w+\})/).map((part, i) => {
    const k = part.match(/^\{(\w+)\}$/)?.[1]
    return k && k in nodes ? <Fragment key={i}>{nodes[k]}</Fragment> : part
  })

/**
 * Connexion avec le compte plex.tv, puis choix du serveur.
 * - Par défaut : code à 4 caractères à saisir sur plex.tv/link (fonctionne partout, même depuis le téléphone).
 * - Alternative : fenêtre de connexion app.plex.tv.
 */
export default function PlexConnect({ settings }) {
  const t = useT()
  const qc = useQueryClient()
  const [phase, setPhase] = useState('idle') // idle | link | window | choose
  const [pin, setPin] = useState(null)
  const [servers, setServers] = useState([])
  const popup = useRef(null)
  const timer = useRef(null)

  useEffect(() => () => clearInterval(timer.current), [])

  const stop = () => {
    clearInterval(timer.current)
    try {
      popup.current?.close()
    } catch {
      /* déjà fermée */
    }
    popup.current = null
  }

  const cancel = (message) => {
    stop()
    setPhase('idle')
    setPin(null)
    if (message) toast(message, 'error')
  }

  const finish = (result) => {
    stop()
    setPin(null)
    setServers(result.servers || [])
    qc.invalidateQueries()
    if (result.selected) {
      setPhase('idle')
      toast(t('Plex connecté — serveur « {name} » ({kind})', { name: result.selected.name, kind: t(KIND_LABEL[result.selected.connection.kind]) }), 'success')
    } else if (!result.servers?.length) {
      setPhase('idle')
      toast(t('Compte Plex connecté, mais aucun serveur trouvé'), 'error')
    } else {
      setPhase('choose')
    }
  }

  // Interroge plex.tv toutes les 2 s jusqu'à validation, expiration ou fermeture de la fenêtre
  const watch = (p) => {
    const deadline = Date.now() + p.expires_in * 1000
    let closedSince = null
    timer.current = setInterval(async () => {
      if (Date.now() > deadline) return cancel(t('Le code Plex a expiré, recommence'))
      try {
        const res = await plex.checkPin(p.id)
        if (res.authorized) return finish(res)
      } catch (e) {
        return cancel(e.message)
      }
      // Fenêtre fermée sans validation : on laisse quelques secondes à plex.tv, puis on abandonne
      if (p.mode === 'window' && popup.current?.closed) {
        closedSince ??= Date.now()
        if (Date.now() - closedSince > 6000) cancel(t('Fenêtre Plex fermée sans connexion validée — réessaie, ou utilise le code plex.tv/link'))
      }
    }, 2000)
  }

  const startLink = async () => {
    try {
      const p = await plex.authPin('link')
      setPin(p)
      setPhase('link')
      copyText(p.code) // sans message : la plupart des navigateurs ne copient que sur un clic
      watch(p)
    } catch (e) {
      toast(e.message, 'error')
    }
  }

  const startWindow = async () => {
    // Fenêtre ouverte immédiatement (sinon bloquée comme pop-up), puis dirigée vers plex.tv
    popup.current = window.open('', 'plex-auth', 'width=520,height=720')
    try {
      const p = await plex.authPin('window')
      if (popup.current) popup.current.location.href = p.auth_url
      else popup.current = window.open(p.auth_url, '_blank')
      setPin(p)
      setPhase('window')
      watch(p)
    } catch (e) {
      cancel(e.message)
    }
  }

  const loadServers = useMutation({
    mutationFn: plex.servers,
    onSuccess: (r) => {
      setServers(r.results)
      setPhase('choose')
    },
    onError: (e) => toast(e.message, 'error'),
  })

  const select = useMutation({
    mutationFn: (machineId) => plex.selectServer(machineId),
    onSuccess: (r) => {
      setPhase('idle')
      toast(t('Serveur « {name} » sélectionné ({kind})', { name: r.name, kind: t(KIND_LABEL[r.connection.kind]) }), 'success')
      qc.invalidateQueries()
    },
    onError: (e) => toast(e.message, 'error'),
  })

  const logout = useMutation({
    mutationFn: plex.logout,
    onSuccess: () => {
      setPhase('idle')
      setServers([])
      toast(t('Plex déconnecté'), 'info')
      qc.invalidateQueries()
    },
  })

  if (phase === 'link' && pin) {
    return (
      <div className="rounded-xl border border-plex/30 bg-plex/5 p-4 text-center">
        <p className="text-sm text-text2">{t('Va sur plex.tv/link (connecté à ton compte Plex) et saisis ce code :')}</p>
        <button
          onClick={async () => {
            const ok = await copyText(pin.code)
            toast(ok ? t('Code copié') : t('Copie impossible : sélectionne le texte et copie-le à la main'), ok ? 'success' : 'error')
          }}
          className="mx-auto mt-3 flex items-center gap-2 rounded-xl bg-bg px-4 py-2"
          title={t('Copier')}
        >
          <span className="select-text font-mono text-3xl font-semibold tracking-[0.3em]">{pin.code}</span>
          <Copy className="h-4 w-4 text-text3" />
        </button>
        <a
          href={pin.link_url}
          target="_blank"
          rel="noreferrer"
          className="mt-4 inline-flex items-center gap-1.5 rounded-xl bg-plex px-4 py-2 text-sm font-medium text-black hover:brightness-110"
        >
          {t('Ouvrir {url}', { url: 'plex.tv/link' })} <ExternalLink className="h-3.5 w-3.5" />
        </a>
        <p className="mt-3 flex items-center justify-center gap-2 text-xs text-text3">
          <Loader2 className="h-3 w-3 animate-spin" /> {t('En attente de ta validation sur Plex…')}
        </p>
        <button onClick={() => cancel()} className="mt-2 text-xs text-text2 hover:text-text">
          {t('Annuler')}
        </button>
      </div>
    )
  }

  if (phase === 'window') {
    return (
      <div className="flex items-center gap-3 rounded-xl bg-bg3 px-3 py-3 text-sm">
        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-plex" />
        <span className="flex-1">{t('Connecte-toi dans la fenêtre Plex. Elle se fermera toute seule une fois terminé.')}</span>
        <Button variant="ghost" size="sm" onClick={() => cancel()}>
          {t('Annuler')}
        </Button>
      </div>
    )
  }

  if (phase === 'choose') {
    return (
      <div className="space-y-2">
        <p className="text-xs font-medium text-text2">{t('Choisis le serveur à utiliser')}</p>
        {servers.map((s) => (
          <button
            key={s.machine_id}
            disabled={!s.connection || select.isPending}
            onClick={() => select.mutate(s.machine_id)}
            className={`flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition disabled:opacity-50 ${
              s.machine_id === settings?.plex_machine_id ? 'border-plex bg-plex/10' : 'border-line bg-bg hover:border-text3'
            }`}
          >
            {s.connection ? <Server className="h-4 w-4 shrink-0 text-plex" /> : <WifiOff className="h-4 w-4 shrink-0 text-text3" />}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">
                {s.name} {!s.owned && <span className="text-xs font-normal text-text3">· {t('partagé avec toi')}</span>}
              </span>
              <span className="block text-[11px] text-text3">{s.connection ? t('Joignable via {kind}', { kind: t(KIND_LABEL[s.connection.kind]) }) : t('Injoignable depuis SynCiné')}</span>
            </span>
            {select.isPending && select.variables === s.machine_id && <Loader2 className="h-4 w-4 animate-spin" />}
          </button>
        ))}
        <Button variant="ghost" size="sm" onClick={() => setPhase('idle')}>
          {t('Fermer')}
        </Button>
      </div>
    )
  }

  if (settings?.plex_account_connected) {
    return (
      <div className="flex flex-wrap items-center gap-2 rounded-xl bg-bg3 px-3 py-2.5">
        <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
        <span className="min-w-0 flex-1 text-sm">
          {t('Compte Plex connecté')}
          {settings.plex_server_name && (
            <>
              {' '}
              {rich(t('· serveur {name}'), { name: <span className="font-medium">{settings.plex_server_name}</span> })}
            </>
          )}
        </span>
        <Button variant="ghost" size="sm" icon={RefreshCw} loading={loadServers.isPending} onClick={() => loadServers.mutate()}>
          {t('Changer de serveur')}
        </Button>
        <Button variant="ghost" size="sm" icon={LogOut} loading={logout.isPending} onClick={() => logout.mutate()}>
          {t('Déconnecter')}
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <Button variant="primary" icon={LogIn} className="w-full justify-center !bg-plex !text-black" onClick={startLink}>
        {t('Se connecter avec Plex')}
      </Button>
      <button onClick={startWindow} className="text-xs text-text2 hover:text-text">
        ▸ {t('Autre méthode : fenêtre de connexion Plex')}
      </button>
    </div>
  )
}
