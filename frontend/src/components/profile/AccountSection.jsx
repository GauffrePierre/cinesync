import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { AlertTriangle, KeyRound, LogOut } from 'lucide-react'
import TwoFactor from './TwoFactor'
import Button from '../ui/Button'
import { auth } from '../../services/auth'
import { usePersonal, useResetSession } from '../../hooks/useAuth'
import Modal from '../ui/Modal'
import { PasswordForm } from '../../pages/Login'
import { toast } from '../../store/uiStore'
import { useT } from '../../i18n'
import Section from './Section'

// Compte connecté : nom affiché, mot de passe, déconnexion
export default function AccountSection({ user }) {
  const t = useT()
  const personal = usePersonal()
  const reset = useResetSession()
  const [name, setName] = useState(user.display_name || '')
  const [pwOpen, setPwOpen] = useState(false)
  const [username, setUsername] = useState(user.username)
  const [removeOpen, setRemoveOpen] = useState(false)
  const [current, setCurrent] = useState('')
  // Version personnelle en accès libre : le premier mot de passe demande un code écrit dans les journaux du
  // serveur (sinon n'importe quel visiteur pourrait le définir à la place du propriétaire)
  const protecting = personal && !user.has_password
  const [code, setCode] = useState('')
  useEffect(() => {
    if (!pwOpen || !protecting) return
    setCode('')
    auth.protectCode().catch((e) => toast(e.message, 'error'))
  }, [pwOpen, protecting])
  const saveName = useMutation({
    mutationFn: () => auth.updateProfile(name),
    onSuccess: (me) => {
      reset(me)
      toast(t('Nom enregistré'), 'success')
    },
    onError: (e) => toast(e.message, 'error'),
  })
  const removePw = useMutation({
    mutationFn: () => auth.removePassword(current),
    onSuccess: (me) => {
      reset(me)
      setRemoveOpen(false)
      setCurrent('')
      toast(personal ? t('Protection retirée : SynCiné est de nouveau en accès libre') : t('Mot de passe supprimé : tu te connectes avec Plex'), 'success')
    },
    onError: (e) => toast(e.message, 'error'),
  })
  const logout = async () => {
    await auth.logout().catch(() => {})
    reset(null)
  }
  const avatar = user.plex?.thumb
  const canLogout = !personal || user.has_password
  // Supprimer le mot de passe : version personnelle (accès libre), ou compte qui peut se connecter avec Plex
  const canRemove = user.has_password && (personal || !!user.plex)
  const pwLabel = user.has_password ? t('Mot de passe') : personal ? t('Protéger par un mot de passe') : t('Créer un mot de passe')
  return (
    <Section title={t('Mon compte')} keywords="compte account mot de passe password identifiant username nom name double authentification two-factor 2fa totp code déconnexion logout sign out">
      <div className="rounded-2xl border border-line bg-bg2 p-4">
        <div className="flex items-center gap-3">
          {avatar ? (
            <img src={avatar} alt="" className="h-11 w-11 rounded-full object-cover" referrerPolicy="no-referrer" />
          ) : (
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-accent/15 font-semibold text-accent2">{user.name[0]?.toUpperCase()}</span>
          )}
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{user.name}</p>
            <p className="truncate text-xs text-text2">
              {[
                user.plex && t('Connexion avec Plex ({name})', { name: user.plex.username }),
                (user.has_password || !user.plex) && t('Identifiant : {name}', { name: user.username }),
                user.is_admin && !personal && t('Administrateur'),
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>
          </div>
          {canLogout && (
            <Button size="sm" variant="ghost" icon={LogOut} onClick={logout}>
              <span className="hidden sm:inline">{t('Se déconnecter')}</span>
            </Button>
          )}
        </div>
        {personal && !user.has_password && (
          <p className="mt-4 flex items-start gap-2 rounded-xl bg-amber-500/10 p-3 text-xs text-text2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
            {t('Accès libre : toute personne qui ouvre SynCiné y accède sans se connecter. Protège-le par un identifiant et un mot de passe, surtout s’il est accessible hors de chez toi.')}
          </p>
        )}
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('Nom affiché')}
            aria-label={t('Nom affiché')}
            className="h-10 w-full min-w-0 shrink-0 rounded-xl border border-line bg-bg px-3 text-sm outline-none focus:border-accent sm:w-auto sm:flex-1"
          />
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => saveName.mutate()} loading={saveName.isPending} disabled={name === (user.display_name || '')}>
              {t('Enregistrer')}
            </Button>
            <Button icon={KeyRound} variant={personal && !user.has_password ? 'primary' : 'secondary'} onClick={() => setPwOpen(true)}>
              {pwLabel}
            </Button>
          </div>
        </div>
        {(!personal || user.has_password) && <TwoFactor user={user} />}
      </div>

      <Modal open={pwOpen} onClose={() => setPwOpen(false)} title={user.has_password ? t('Changer de mot de passe') : pwLabel}>
        {!user.has_password && (
          <p className="mb-4 text-sm text-text2">
            {personal
              ? t('SynCiné demandera cet identifiant et ce mot de passe sur chaque appareil. Cet appareil-ci reste connecté.')
              : user.plex
                ? t('En plus de Plex, tu pourras te connecter avec cet identifiant et ce mot de passe.')
                : t('Choisis ton identifiant et ton mot de passe de connexion.')}
          </p>
        )}
        <PasswordForm
          needCurrent={user.has_password}
          code={protecting ? code : undefined}
          beforeSubmit={!user.has_password && username.trim().toLowerCase() !== user.username ? () => auth.updateProfile(name, username) : undefined}
          onDone={(me) => {
            reset(me)
            setPwOpen(false)
            toast(user.has_password ? t('Mot de passe enregistré — tes autres appareils ont été déconnectés') : t('Mot de passe enregistré'), 'success')
          }}
        >
          {!user.has_password && (
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium">{t('Identifiant')}</span>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoCapitalize="none"
                required
                className="h-11 w-full rounded-xl border border-line bg-bg px-3 text-sm outline-none focus:border-accent"
              />
            </label>
          )}
          {protecting && (
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium">{t('Code de sécurité')}</span>
              <input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                autoComplete="one-time-code"
                autoCapitalize="characters"
                placeholder="XXXX-XXXX-XXXX"
                required
                className="h-11 w-full rounded-xl border border-line bg-bg px-3 font-mono text-sm outline-none focus:border-accent"
              />
              <span className="mt-1.5 block text-xs text-text2">
                {t('SynCiné vient d’écrire ce code dans les journaux du serveur (journaux du conteneur). Il prouve que tu as la main sur le serveur.')}
              </span>
            </label>
          )}
        </PasswordForm>
        {canRemove && (
          <button onClick={() => { setPwOpen(false); setRemoveOpen(true) }} className="mt-4 block w-full text-center text-xs text-text3 hover:text-red-400">
            {personal ? t('Retirer la protection par mot de passe') : t('Supprimer mon mot de passe (connexion avec Plex uniquement)')}
          </button>
        )}
      </Modal>

      <Modal open={removeOpen} onClose={() => setRemoveOpen(false)} title={personal ? t('Retirer la protection ?') : t('Supprimer ton mot de passe ?')}>
        <p className="mb-4 text-sm text-text2">
          {personal ? t('SynCiné redeviendra accessible sans connexion, à toute personne qui l’ouvre.') : t('Tu te connecteras uniquement avec ton compte Plex.')}
        </p>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            removePw.mutate()
          }}
        >
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            placeholder={t('Mot de passe actuel')}
            aria-label={t('Mot de passe actuel')}
            autoComplete="current-password"
            required
            className="h-11 w-full rounded-xl border border-line bg-bg px-3 text-sm outline-none focus:border-accent"
          />
          <div className="flex justify-end gap-2">
            <Button type="button" onClick={() => setRemoveOpen(false)}>
              {t('Annuler')}
            </Button>
            <Button type="submit" variant="danger" loading={removePw.isPending}>
              {personal ? t('Retirer la protection') : t('Supprimer')}
            </Button>
          </div>
        </form>
      </Modal>
    </Section>
  )
}
