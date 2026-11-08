import { useEffect, useRef, useState } from 'react'
import { ExternalLink, KeyRound, Loader2, LogIn, ShieldCheck } from 'lucide-react'
import Logo from '../components/layout/Logo'
import Button from '../components/ui/Button'
import { auth } from '../services/auth'
import { useResetSession } from '../hooks/useAuth'
import { useSettingsStore } from '../store/settingsStore'
import { UI_LANGUAGES, useT } from '../i18n'

// Écrans hors application : installation (compte admin), connexion, mot de passe provisoire à changer

function Shell({ title, subtitle, children }) {
  const t = useT()
  const lang = useSettingsStore((s) => s.uiLanguage || 'fr')
  const setLang = useSettingsStore((s) => s.setUiLanguage)
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-bg px-4 py-10 text-text">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <Logo />
        </div>
        <div className="rounded-2xl border border-line bg-bg2 p-6 shadow-sm">
          <h1 className="text-center text-xl font-semibold">{title}</h1>
          {subtitle && <p className="mt-1 text-center text-sm text-text2">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </div>
        <div className="mt-6 flex justify-center gap-1 text-xs" aria-label={t("Langue de l'interface")}>
          {UI_LANGUAGES.map((l) => (
            <button
              key={l.code}
              onClick={() => setLang(l.code)}
              className={`rounded-lg px-2.5 py-1 ${lang === l.code ? 'bg-bg3 text-text' : 'text-text3 hover:text-text2'}`}
            >
              {l.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function Field({ label, hint, ...props }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium">{label}</span>
      <input
        {...props}
        className="h-11 w-full rounded-xl border border-line bg-bg px-3 text-sm outline-none placeholder:text-text3 focus:border-accent"
      />
      {hint && <span className="mt-1 block text-xs text-text3">{hint}</span>}
    </label>
  )
}

function ErrorLine({ error }) {
  if (!error) return null
  return (
    <p role="alert" className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">
      {error}
    </p>
  )
}

function Divider() {
  const t = useT()
  return (
    <div className="my-5 flex items-center gap-3 text-xs text-text3">
      <span className="h-px flex-1 bg-line" />
      {t('ou')}
      <span className="h-px flex-1 bg-line" />
    </div>
  )
}

/**
 * Connexion avec Plex : code à saisir sur plex.tv/link (fiable partout) ou fenêtre app.plex.tv.
 * Le serveur vérifie ensuite que ce compte Plex fait partie de ceux autorisés par l'administrateur.
 */
function PlexLogin({ onDone, label }) {
  const t = useT()
  const [pin, setPin] = useState(null)
  const [error, setError] = useState(null)
  const timer = useRef(null)
  const popup = useRef(null)

  useEffect(() => () => clearInterval(timer.current), [])

  const stop = (message) => {
    clearInterval(timer.current)
    try {
      popup.current?.close()
    } catch {
      /* déjà fermée */
    }
    popup.current = null
    setPin(null)
    if (message) setError(message)
  }

  const watch = (p) => {
    const deadline = Date.now() + p.expires_in * 1000
    timer.current = setInterval(async () => {
      if (Date.now() > deadline) return stop(t('Le code Plex a expiré, recommence'))
      try {
        const res = await auth.plexCheck(p.id)
        if (res.authorized) {
          stop()
          onDone(res)
        }
      } catch (e) {
        stop(e.message)
      }
    }, 2000)
  }

  const start = async (mode) => {
    setError(null)
    if (mode === 'window') popup.current = window.open('', 'plex-auth', 'width=520,height=720')
    try {
      const p = await auth.plexPin(mode)
      if (mode === 'window') {
        if (popup.current) popup.current.location.href = p.auth_url
        else popup.current = window.open(p.auth_url, '_blank')
      }
      setPin(p)
      watch(p)
    } catch (e) {
      stop(e.message)
    }
  }

  if (pin?.mode === 'link') {
    return (
      <div className="space-y-3 text-center">
        <p className="text-sm text-text2">{t('Sur plex.tv/link, saisis ce code :')}</p>
        <p className="font-mono text-3xl font-semibold tracking-[0.3em]">{pin.code}</p>
        <a href={pin.link_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-accent2 hover:underline">
          {t('Ouvrir plex.tv/link')} <ExternalLink className="h-3.5 w-3.5" />
        </a>
        <p className="flex items-center justify-center gap-2 text-xs text-text3">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> {t('En attente de la validation sur plex.tv…')}
        </p>
        <button onClick={() => stop()} className="text-xs text-text3 hover:text-text2">
          {t('Annuler')}
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <ErrorLine error={error} />
      <Button className="w-full" variant="secondary" onClick={() => start('link')} loading={pin?.mode === 'window'}>
        <span className="flex h-4 w-4 items-center justify-center rounded-full bg-plex text-black">
          <svg viewBox="0 0 24 24" className="h-2.5 w-2.5" fill="currentColor" aria-hidden="true">
            <path d="M8 3h5l6 9-6 9H8l6-9z" />
          </svg>
        </span>
        {label || t('Se connecter avec Plex')}
      </Button>
      <button onClick={() => start('window')} className="block w-full text-center text-xs text-text3 hover:text-text2">
        {t('ou ouvrir la fenêtre de connexion Plex')}
      </button>
    </div>
  )
}

/** Deuxième étape de connexion (2FA activée) : code à 6 chiffres de l'application, ou code de secours. */
function TwoFactorStep({ ticket, onDone, onCancel }) {
  const t = useT()
  const [code, setCode] = useState('')
  const [recovery, setRecovery] = useState(false)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onDone(await auth.loginTwoFactor(ticket, code))
    } catch (err) {
      if (err.status === 410) return onCancel(err.message)
      setError(err.message)
      setCode('')
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <p className="text-center text-sm text-text2">
        {recovery
          ? t('Saisis l’un de tes codes de secours (chacun ne sert qu’une fois).')
          : t('Saisis le code à 6 chiffres affiché par ton application d’authentification.')}
      </p>
      <Field
        label={recovery ? t('Code de secours') : t('Code de vérification')}
        value={code}
        onChange={(e) => setCode(e.target.value)}
        inputMode={recovery ? 'text' : 'numeric'}
        autoComplete="one-time-code"
        autoCapitalize="none"
        placeholder={recovery ? 'xxxx-xxxx' : '123456'}
        maxLength={recovery ? 12 : 7}
        autoFocus
        required
      />
      <ErrorLine error={error} />
      <Button type="submit" variant="primary" className="w-full" loading={busy}>
        <ShieldCheck className="h-4 w-4" /> {t('Vérifier')}
      </Button>
      <div className="flex justify-between text-xs">
        <button type="button" onClick={() => { setRecovery((r) => !r); setCode(''); setError(null) }} className="text-text3 hover:text-text2">
          {recovery ? t('Utiliser l’application') : t('Utiliser un code de secours')}
        </button>
        <button type="button" onClick={() => onCancel()} className="text-text3 hover:text-text2">
          {t('Annuler')}
        </button>
      </div>
    </form>
  )
}

export function Setup({ me }) {
  const t = useT()
  const reset = useResetSession()
  const [form, setForm] = useState({ code: '', username: '', display_name: '', password: '', confirm: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    if (form.password !== form.confirm) return setError(t('Les deux mots de passe ne correspondent pas'))
    setBusy(true)
    setError(null)
    try {
      reset(await auth.setup({ code: form.code, username: form.username, display_name: form.display_name, password: form.password }))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Shell title={t('Bienvenue sur SynCiné')} subtitle={t('Crée le compte administrateur. Tu pourras ensuite ajouter les comptes de la famille.')}>
      <form onSubmit={submit} className="space-y-4">
        <Field
          label={t("Code d'installation")}
          hint={t('Affiché dans les journaux du conteneur cinesync-backend (sur Unraid : icône du conteneur → Logs).')}
          value={form.code}
          onChange={set('code')}
          placeholder="XXXX-XXXX-XXXX"
          autoComplete="off"
          required
        />
        <Field label={t('Identifiant')} value={form.username} onChange={set('username')} autoComplete="username" autoCapitalize="none" required />
        <Field label={t('Nom affiché')} value={form.display_name} onChange={set('display_name')} placeholder={t('Facultatif')} />
        <Field label={t('Mot de passe')} hint={t('8 caractères minimum')} type="password" value={form.password} onChange={set('password')} autoComplete="new-password" required />
        <Field label={t('Confirmer le mot de passe')} type="password" value={form.confirm} onChange={set('confirm')} autoComplete="new-password" required />
        <ErrorLine error={error} />
        <Button type="submit" variant="primary" className="w-full" loading={busy}>
          <ShieldCheck className="h-4 w-4" /> {t('Créer le compte administrateur')}
        </Button>
      </form>
      {me.plex_login && (
        <>
          <Divider />
          <p className="mb-3 text-xs text-text2">{t('Ton compte Plex est déjà relié à SynCiné : tu peux aussi devenir administrateur en te connectant avec lui.')}</p>
          <PlexLogin onDone={reset} label={t('Continuer avec mon compte Plex')} />
        </>
      )}
    </Shell>
  )
}

export function Login({ me }) {
  const t = useT()
  const reset = useResetSession()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [ticket, setTicket] = useState(null)

  // Mot de passe ou Plex validé : session ouverte, ou code de double authentification demandé
  const done = (res) => {
    if (res.two_factor_required) {
      setTicket(res.ticket)
      setBusy(false)
    } else reset(res)
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      done(await auth.login(username, password))
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  if (ticket) {
    return (
      <Shell title={t('Double authentification')}>
        <TwoFactorStep
          ticket={ticket}
          onDone={reset}
          onCancel={(message) => {
            setTicket(null)
            setPassword('')
            setError(message || null)
          }}
        />
      </Shell>
    )
  }

  return (
    <Shell title={t('Connexion')}>
      {me.plex_login && (
        <>
          <PlexLogin onDone={done} />
          <Divider />
        </>
      )}
      <form onSubmit={submit} className="space-y-4">
        <Field label={t('Identifiant')} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoCapitalize="none" required />
        <Field label={t('Mot de passe')} type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        <ErrorLine error={error} />
        <Button type="submit" variant="primary" className="w-full" loading={busy}>
          <LogIn className="h-4 w-4" /> {t('Se connecter')}
        </Button>
      </form>
    </Shell>
  )
}

// Formulaire de changement de mot de passe : écran imposé (mot de passe provisoire) ou dans le Profil
export function PasswordForm({ needCurrent, onDone, submitLabel, beforeSubmit, children }) {
  const t = useT()
  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    if (form.next !== form.confirm) return setError(t('Les deux mots de passe ne correspondent pas'))
    setBusy(true)
    setError(null)
    try {
      if (beforeSubmit) await beforeSubmit()
      const me = await auth.changePassword(form.current, form.next)
      setForm({ current: '', next: '', confirm: '' })
      onDone?.(me)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {children}
      {needCurrent && (
        <Field label={t('Mot de passe actuel')} type="password" value={form.current} onChange={set('current')} autoComplete="current-password" required />
      )}
      <Field label={t('Nouveau mot de passe')} hint={t('8 caractères minimum')} type="password" value={form.next} onChange={set('next')} autoComplete="new-password" required />
      <Field label={t('Confirmer le mot de passe')} type="password" value={form.confirm} onChange={set('confirm')} autoComplete="new-password" required />
      <ErrorLine error={error} />
      <Button type="submit" variant="primary" className="w-full" loading={busy}>
        <KeyRound className="h-4 w-4" /> {submitLabel || t('Enregistrer le mot de passe')}
      </Button>
    </form>
  )
}

export function ForcePasswordChange({ me }) {
  const t = useT()
  const reset = useResetSession()
  return (
    <Shell
      title={t('Choisis ton mot de passe')}
      subtitle={t('Bonjour {name} ! Ton mot de passe actuel est provisoire : remplace-le par un mot de passe que toi seul connais.', { name: me.user.name })}
    >
      <PasswordForm onDone={reset} submitLabel={t('Continuer')} />
      <button
        onClick={async () => {
          await auth.logout().catch(() => {})
          reset(null)
        }}
        className="mt-4 block w-full text-center text-xs text-text3 hover:text-text2"
      >
        {t('Se déconnecter')}
      </button>
    </Shell>
  )
}

export function Splash({ error, onRetry }) {
  const t = useT()
  if (!error) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-bg">
        <Loader2 className="h-6 w-6 animate-spin text-text3" />
      </div>
    )
  }
  return (
    <Shell title={t('SynCiné injoignable')} subtitle={error.message}>
      <Button variant="primary" className="w-full" onClick={onRetry}>
        {t('Réessayer')}
      </Button>
    </Shell>
  )
}
