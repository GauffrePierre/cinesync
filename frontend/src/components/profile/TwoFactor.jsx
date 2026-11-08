import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Copy, Download, ShieldCheck, ShieldOff } from 'lucide-react'
import Button from '../ui/Button'
import Modal from '../ui/Modal'
import { auth } from '../../services/auth'
import { toast } from '../../store/uiStore'
import { useT } from '../../i18n'

// Double authentification (TOTP) du compte : activation avec une application (Aegis, Google Authenticator,
// Bitwarden…), codes de secours, désactivation. Le QR code est fabriqué par le serveur SynCiné.

const input = 'h-11 w-full rounded-xl border border-line bg-bg px-3 text-sm outline-none focus:border-accent'

function RecoveryCodes({ codes, onDone }) {
  const t = useT()
  const text = codes.join('\n')
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      toast(t('Codes copiés'), 'success')
    } catch {
      toast(t('Copie impossible : note-les à la main'), 'error')
    }
  }
  const download = () => {
    const url = URL.createObjectURL(new Blob([`SynCiné\n${text}\n`], { type: 'text/plain' }))
    const a = Object.assign(document.createElement('a'), { href: url, download: 'syncine-codes-de-secours.txt' })
    a.click()
    URL.revokeObjectURL(url)
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-text2">
        {t('Garde ces codes de secours en lieu sûr (gestionnaire de mots de passe, papier) : chacun permet une connexion si tu perds ton téléphone. Ils ne seront plus affichés.')}
      </p>
      <ul className="grid grid-cols-2 gap-2 rounded-xl bg-bg3 p-3 font-mono text-sm">
        {codes.map((c) => (
          <li key={c} className="text-center">
            {c}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap justify-end gap-2">
        <Button icon={Copy} onClick={copy}>
          {t('Copier')}
        </Button>
        <Button icon={Download} onClick={download}>
          {t('Télécharger')}
        </Button>
        <Button variant="primary" onClick={onDone}>
          {t("C'est noté")}
        </Button>
      </div>
    </div>
  )
}

function CodeForm({ label, danger, onSubmit, busy }) {
  const t = useT()
  const [code, setCode] = useState('')
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit(code, () => setCode(''))
      }}
    >
      <input
        value={code}
        onChange={(e) => setCode(e.target.value)}
        placeholder={t('Code à 6 chiffres ou code de secours')}
        aria-label={t('Code de vérification')}
        autoComplete="one-time-code"
        autoCapitalize="none"
        maxLength={12}
        autoFocus
        required
        className={input}
      />
      <div className="flex justify-end">
        <Button type="submit" variant={danger ? 'danger' : 'primary'} loading={busy}>
          {label}
        </Button>
      </div>
    </form>
  )
}

export default function TwoFactor({ user }) {
  const t = useT()
  const qc = useQueryClient()
  const reset = (me) => qc.setQueryData(['me'], me) // même compte : les autres données restent valables
  const [step, setStep] = useState(null) // confirm | setup | codes | disable | renew
  const [password, setPassword] = useState('')
  const [setup, setSetup] = useState(null)
  const [codes, setCodes] = useState(null)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)

  const close = () => {
    setStep(null)
    setSetup(null)
    setCodes(null)
    setCode('')
    setPassword('')
  }
  const run = async (fn) => {
    setBusy(true)
    try {
      await fn()
    } catch (e) {
      toast(e.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  // Mot de passe actuel demandé d'abord (sans mot de passe, compte Plex : connexion récente vérifiée par le serveur)
  const start = () => (user.has_password ? setStep('confirm') : begin())
  const begin = (e) => {
    e?.preventDefault()
    run(async () => {
      setSetup(await auth.twoFactorSetup(password))
      setPassword('')
      setStep('setup')
    })
  }
  const enable = (e) => {
    e.preventDefault()
    run(async () => {
      const res = await auth.twoFactorEnable(code)
      setCodes(res.recovery_codes)
      setStep('codes')
      const { recovery_codes: _, ...me } = res
      reset(me)
      toast(t('Double authentification activée'), 'success')
    })
  }
  const disable = (value, clear) =>
    run(async () => {
      try {
        reset(await auth.twoFactorDisable(value))
        close()
        toast(t('Double authentification désactivée'), 'success')
      } finally {
        clear()
      }
    })
  const renew = (value, clear) =>
    run(async () => {
      try {
        setCodes((await auth.twoFactorRecoveryCodes(value)).recovery_codes)
        setStep('codes')
      } finally {
        clear()
      }
    })

  return (
    <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4">
      {user.two_factor ? <ShieldCheck className="h-5 w-5 shrink-0 text-emerald-500" /> : <ShieldOff className="h-5 w-5 shrink-0 text-text3" />}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{t('Double authentification')}</p>
        <p className="text-xs text-text2">
          {user.two_factor ? t('Activée : un code de ton application est demandé à chaque connexion.') : t('Un code de ton téléphone en plus du mot de passe (ou de Plex).')}
        </p>
      </div>
      {user.two_factor ? (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => setStep('renew')}>
            {t('Codes de secours')}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setStep('disable')}>
            {t('Désactiver')}
          </Button>
        </div>
      ) : (
        <Button size="sm" icon={ShieldCheck} onClick={start} loading={busy && !step}>
          {t('Activer')}
        </Button>
      )}

      <Modal open={step === 'confirm'} onClose={close} title={t('Activer la double authentification')}>
        <form className="space-y-4" onSubmit={begin}>
          <p className="text-sm text-text2">{t('Confirme ton mot de passe actuel pour continuer.')}</p>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t('Mot de passe actuel')}
            aria-label={t('Mot de passe actuel')}
            autoComplete="current-password"
            autoFocus
            required
            className={input}
          />
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={close}>
              {t('Annuler')}
            </Button>
            <Button type="submit" variant="primary" loading={busy}>
              {t('Continuer')}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal open={step === 'setup'} onClose={close} title={t('Activer la double authentification')}>
        {setup && (
          <form className="space-y-4" onSubmit={enable}>
            <p className="text-sm text-text2">
              {t('1. Scanne ce QR code avec ton application d’authentification (Aegis, Google Authenticator, Bitwarden, 1Password…).')}
            </p>
            <img src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(setup.qr_svg)}`} alt={t('QR code à scanner')} className="mx-auto h-48 w-48 rounded-xl bg-white p-1" />
            <details className="text-xs text-text2">
              <summary className="cursor-pointer">{t('Impossible de scanner ? Saisis la clé à la main')}</summary>
              <p className="mt-2 select-all break-all rounded-lg bg-bg3 p-2 font-mono">{setup.secret.match(/.{1,4}/g).join(' ')}</p>
              <a href={setup.uri} className="mt-2 inline-block text-accent2 hover:underline">
                {t("Ouvrir dans l'application de ce téléphone")}
              </a>
            </details>
            <p className="text-sm text-text2">{t('2. Saisis le code à 6 chiffres affiché par l’application :')}</p>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="123456"
              aria-label={t('Code de vérification')}
              maxLength={7}
              required
              className={input}
            />
            <div className="flex justify-end gap-2">
              <Button type="button" onClick={close}>
                {t('Annuler')}
              </Button>
              <Button type="submit" variant="primary" loading={busy}>
                {t('Activer')}
              </Button>
            </div>
          </form>
        )}
      </Modal>

      <Modal open={step === 'codes'} onClose={close} title={t('Codes de secours')}>
        {codes && <RecoveryCodes codes={codes} onDone={close} />}
      </Modal>

      <Modal open={step === 'renew'} onClose={close} title={t('Nouveaux codes de secours')}>
        <p className="mb-4 text-sm text-text2">{t('Les anciens codes de secours ne fonctionneront plus.')}</p>
        <CodeForm label={t('Générer')} onSubmit={renew} busy={busy} />
      </Modal>

      <Modal open={step === 'disable'} onClose={close} title={t('Désactiver la double authentification ?')}>
        <p className="mb-4 text-sm text-text2">{t('Ton compte ne sera plus protégé que par ton mot de passe (ou Plex).')}</p>
        <CodeForm label={t('Désactiver')} danger onSubmit={disable} busy={busy} />
      </Modal>
    </div>
  )
}
