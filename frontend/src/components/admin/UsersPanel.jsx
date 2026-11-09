import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, KeyRound, MoreHorizontal, Plus, RefreshCw, Shield, ShieldOff, Trash2, UserCheck, UserX } from 'lucide-react'
import Button from '../ui/Button'
import Modal from '../ui/Modal'
import Skeleton from '../ui/Skeleton'
import { admin } from '../../services/admin'
import { jellyfin } from '../../services/jellyfin'
import { useCurrentUser } from '../../hooks/useAuth'
import { useStatus } from '../../hooks/useMedia'
import { relativeTime } from '../../lib/format'
import { toast } from '../../store/uiStore'
import { useT } from '../../i18n'

const randomPassword = () => {
  const chars = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  const bytes = crypto.getRandomValues(new Uint8Array(12))
  return Array.from(bytes, (b) => chars[b % chars.length]).join('')
}

function Avatar({ user, thumb }) {
  const src = thumb || user?.plex?.thumb
  const name = user?.name || '?'
  return src ? (
    <img src={src} alt="" className="h-9 w-9 shrink-0 rounded-full object-cover" referrerPolicy="no-referrer" />
  ) : (
    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent/15 text-sm font-semibold text-accent2">{name[0]?.toUpperCase()}</span>
  )
}

function Input({ label, hint, right, ...props }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium">{label}</span>
      <span className="flex gap-2">
        <input {...props} className="h-10 w-full min-w-0 rounded-xl border border-line bg-bg px-3 text-sm outline-none focus:border-accent" />
        {right}
      </span>
      {hint && <span className="mt-1 block text-xs text-text3">{hint}</span>}
    </label>
  )
}

function Check2({ label, checked, onChange }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="h-4 w-4 accent-[var(--color-accent,#6c63ff)]" />
      {label}
    </label>
  )
}

function PasswordInput({ value, onChange, label }) {
  const t = useT()
  return (
    <Input
      label={label}
      hint={t('À transmettre à la personne : elle devra le changer à sa première connexion.')}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      autoComplete="off"
      required
      minLength={8}
      right={
        <Button type="button" size="md" icon={RefreshCw} onClick={() => onChange(randomPassword())}>
          {t('Générer')}
        </Button>
      }
    />
  )
}

function useRefresh() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: ['admin', 'users'] })
    qc.invalidateQueries({ queryKey: ['admin', 'plex-accounts'] })
  }
}

function AddUserModal({ open, onClose }) {
  const t = useT()
  const refresh = useRefresh()
  const [form, setForm] = useState({ username: '', display_name: '', password: randomPassword(), role: 'member', can_request_direct: false })
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }))
  const create = useMutation({
    mutationFn: () => admin.createUser(form),
    onSuccess: (u) => {
      toast(t('Compte « {name} » créé', { name: u.name }), 'success')
      refresh()
      onClose()
      setForm({ username: '', display_name: '', password: randomPassword(), role: 'member', can_request_direct: false })
    },
    onError: (e) => toast(e.message, 'error'),
  })
  return (
    <Modal open={open} onClose={onClose} title={t('Ajouter un compte')}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          create.mutate()
        }}
      >
        <Input label={t('Identifiant')} value={form.username} onChange={(e) => set('username')(e.target.value)} autoCapitalize="none" autoComplete="off" required />
        <Input label={t('Nom affiché')} value={form.display_name} onChange={(e) => set('display_name')(e.target.value)} />
        <PasswordInput label={t('Mot de passe provisoire')} value={form.password} onChange={set('password')} />
        <div className="space-y-2">
          <Check2 label={t('Demandes envoyées directement à Seerr')} checked={form.can_request_direct} onChange={set('can_request_direct')} />
          <Check2 label={t('Administrateur')} checked={form.role === 'admin'} onChange={(v) => set('role')(v ? 'admin' : 'member')} />
        </div>
        <Button type="submit" variant="primary" className="w-full justify-center" loading={create.isPending} icon={Plus}>
          {t('Créer le compte')}
        </Button>
      </form>
    </Modal>
  )
}

function ResetPasswordModal({ user, onClose }) {
  const t = useT()
  const [password, setPassword] = useState(randomPassword())
  const reset = useMutation({
    mutationFn: () => admin.updateUser(user.id, { password }),
    onSuccess: () => {
      toast(t('Mot de passe provisoire enregistré'), 'success')
      onClose()
    },
    onError: (e) => toast(e.message, 'error'),
  })
  return (
    <Modal open={!!user} onClose={onClose} title={t('Nouveau mot de passe pour {name}', { name: user?.name || '' })}>
      {user && !user.has_password && user.plex && (
        <p className="mb-4 text-sm text-text2">
          {t('{name} pourra aussi se connecter avec son identifiant « {username} » et ce mot de passe, en plus de Plex.', { name: user.name, username: user.username })}
        </p>
      )}
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          reset.mutate()
        }}
      >
        <PasswordInput label={t('Mot de passe provisoire')} value={password} onChange={setPassword} />
        <p className="text-xs text-text3">{t('Ses appareils connectés seront déconnectés.')}</p>
        <Button type="submit" variant="primary" className="w-full justify-center" loading={reset.isPending} icon={KeyRound}>
          {t('Enregistrer')}
        </Button>
      </form>
    </Modal>
  )
}

function DeleteModal({ user, onClose }) {
  const t = useT()
  const refresh = useRefresh()
  const del = useMutation({
    mutationFn: () => admin.deleteUser(user.id),
    onSuccess: () => {
      toast(t('Compte supprimé'), 'success')
      refresh()
      onClose()
    },
    onError: (e) => toast(e.message, 'error'),
  })
  return (
    <Modal open={!!user} onClose={onClose} title={t('Supprimer le compte de {name} ?', { name: user?.name || '' })}>
      <p className="text-sm text-text2">
        {t('Sa watchlist, ses notes, son historique SynCiné, ses notifications et ses demandes seront supprimés. Ses comptes Trakt, Plex et Letterboxd ne sont pas touchés.')}
      </p>
      <div className="mt-5 flex justify-end gap-2">
        <Button onClick={onClose}>{t('Annuler')}</Button>
        <Button variant="danger" icon={Trash2} loading={del.isPending} onClick={() => del.mutate()}>
          {t('Supprimer')}
        </Button>
      </div>
    </Modal>
  )
}

function UserRow({ user, me, onReset, onDelete }) {
  const t = useT()
  const refresh = useRefresh()
  const [menu, setMenu] = useState(false)
  const update = useMutation({
    mutationFn: (patch) => admin.updateUser(user.id, patch),
    onSuccess: refresh,
    onError: (e) => toast(e.message, 'error'),
  })
  const self = user.id === me?.id
  const item = 'flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-bg3'
  return (
    <li className={`flex items-center gap-3 py-3 first:pt-0 last:pb-0 ${user.active ? '' : 'opacity-60'}`}>
      <Avatar user={user} />
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-1.5 text-sm font-medium">
          <span className="truncate">{user.name}</span>
          {self && <span className="text-xs font-normal text-text3">({t('toi')})</span>}
          {user.is_admin && <span className="rounded-md bg-accent/15 px-1.5 py-0.5 text-[10px] font-medium text-accent2">{t('Admin')}</span>}
          {user.plex && <span className="rounded-md bg-plex/15 px-1.5 py-0.5 text-[10px] font-medium text-plex">Plex</span>}
          {user.jellyfin && <span className="rounded-md bg-[#aa5cc3]/15 px-1.5 py-0.5 text-[10px] font-medium text-[#c287d6]">Jellyfin</span>}
          {user.two_factor && <span className="rounded-md bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-medium text-emerald-500">2FA</span>}
          {!user.active && <span className="rounded-md bg-bg3 px-1.5 py-0.5 text-[10px] font-medium text-text2">{t('Désactivé')}</span>}
        </p>
        <p className="truncate text-xs text-text3">
          {user.username}
          {' · '}
          {user.last_login_at ? t('connecté {when}', { when: relativeTime(user.last_login_at) }) : t('jamais connecté')}
          {user.must_change_password && ` · ${t('mot de passe provisoire')}`}
        </p>
        {!user.is_admin && (
          <label className="mt-1.5 flex items-center gap-2 text-xs text-text2">
            <input type="checkbox" checked={user.can_request_direct} onChange={(e) => update.mutate({ can_request_direct: e.target.checked })} className="h-3.5 w-3.5" />
            {t('Demandes envoyées directement à Seerr')}
          </label>
        )}
      </div>
      {!self && (
        <div className="relative">
          <Button size="sm" variant="ghost" aria-label={t('Actions')} onClick={() => setMenu((m) => !m)}>
            <MoreHorizontal className="h-4 w-4" />
          </Button>
          {menu && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setMenu(false)} />
              <div className="absolute right-0 z-20 mt-1 w-56 rounded-xl border border-line bg-bg2 p-1 shadow-xl" onClick={() => setMenu(false)}>
                <button className={item} onClick={() => update.mutate({ role: user.is_admin ? 'member' : 'admin' })}>
                  <Shield className="h-4 w-4" /> {user.is_admin ? t('Retirer les droits admin') : t('Rendre administrateur')}
                </button>
                <button className={item} onClick={() => onReset(user)}>
                  <KeyRound className="h-4 w-4" /> {user.has_password ? t('Nouveau mot de passe provisoire') : t('Donner un mot de passe')}
                </button>
                {user.two_factor && (
                  <button
                    className={item}
                    onClick={() => {
                      if (window.confirm(t('Désactiver la double authentification de {name} (téléphone perdu) ?', { name: user.name }))) {
                        update.mutate({ reset_two_factor: true }, { onSuccess: () => toast(t('Double authentification désactivée'), 'success') })
                      }
                    }}
                  >
                    <ShieldOff className="h-4 w-4" /> {t('Réinitialiser la double authentification')}
                  </button>
                )}
                <button className={item} onClick={() => update.mutate({ active: !user.active })}>
                  {user.active ? <UserX className="h-4 w-4" /> : <UserCheck className="h-4 w-4" />}
                  {user.active ? t('Désactiver') : t('Réactiver')}
                </button>
                <button className={`${item} text-red-500`} onClick={() => onDelete(user)}>
                  <Trash2 className="h-4 w-4" /> {t('Supprimer')}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </li>
  )
}

function PlexAccounts() {
  const t = useT()
  const refresh = useRefresh()
  const [allowing, setAllowing] = useState(null)
  const [form, setForm] = useState({ display_name: '', can_request_direct: false, withPassword: false, password: '' })
  const { data, error, isLoading } = useQuery({ queryKey: ['admin', 'plex-accounts'], queryFn: admin.plexAccounts, staleTime: 60_000, retry: false })
  const allow = useMutation({
    mutationFn: () =>
      admin.allowPlex({
        plex_user_id: allowing.id,
        display_name: form.display_name,
        can_request_direct: form.can_request_direct,
        password: form.withPassword ? form.password : null,
      }),
    onSuccess: (u) => {
      toast(t('{name} peut se connecter avec Plex', { name: u.name }), 'success')
      refresh()
      setAllowing(null)
    },
    onError: (e) => toast(e.message, 'error'),
  })

  if (isLoading) return <Skeleton className="h-24" />
  if (error) return <p className="rounded-xl bg-bg3/60 p-3 text-sm text-text2">{error.message}</p>
  const list = data?.results || []
  return (
    <>
      <ul className="divide-y divide-line">
        {list.map((a) => {
          const allowed = a.user && a.user.active
          return (
            <li key={a.id} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
              <Avatar user={{ name: a.title }} thumb={a.thumb} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{a.title}</p>
                <p className="truncate text-xs text-text3">
                  {a.owner ? t('Propriétaire du serveur') : a.home ? t('Foyer Plex') : t('Ami Plex')}
                  {a.username && a.username !== a.title ? ` · ${a.username}` : ''}
                </p>
              </div>
              {allowed ? (
                <span className="flex items-center gap-1 text-xs font-medium text-emerald-500">
                  <Check className="h-4 w-4" /> {t('Autorisé')}
                </span>
              ) : (
                <Button
                  size="sm"
                  onClick={() => {
                    setForm({ display_name: a.title, can_request_direct: false, withPassword: false, password: randomPassword() })
                    setAllowing(a)
                  }}
                >
                  {a.user ? t('Réactiver') : t('Autoriser')}
                </Button>
              )}
            </li>
          )
        })}
      </ul>
      <Modal open={!!allowing} onClose={() => setAllowing(null)} title={t('Autoriser {name}', { name: allowing?.title || '' })}>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            allow.mutate()
          }}
        >
          <Input label={t('Nom affiché')} value={form.display_name} onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))} />
          <Check2 label={t('Demandes envoyées directement à Seerr')} checked={form.can_request_direct} onChange={(v) => setForm((f) => ({ ...f, can_request_direct: v }))} />
          <Check2 label={t('Permettre aussi la connexion par identifiant et mot de passe')} checked={form.withPassword} onChange={(v) => setForm((f) => ({ ...f, withPassword: v }))} />
          {form.withPassword && <PasswordInput label={t('Mot de passe provisoire')} value={form.password} onChange={(v) => setForm((f) => ({ ...f, password: v }))} />}
          <p className="text-xs text-text3">{t("Cette personne se connectera avec « Se connecter avec Plex ». SynCiné vérifie que c'est bien ce compte Plex.")}</p>
          <Button type="submit" variant="primary" className="w-full justify-center" loading={allow.isPending} icon={Check}>
            {t('Autoriser')}
          </Button>
        </form>
      </Modal>
    </>
  )
}

// Comptes du serveur Jellyfin / Emby : autoriser ceux qui peuvent se connecter avec leur compte
function JellyfinAccounts() {
  const t = useT()
  const refresh = useRefresh()
  const qc = useQueryClient()
  const { data, error, isLoading } = useQuery({ queryKey: ['admin', 'jellyfin-accounts'], queryFn: jellyfin.users, staleTime: 60_000, retry: false })
  const allow = useMutation({
    mutationFn: (a) => admin.allowJellyfin({ jellyfin_user_id: a.id, display_name: a.name }),
    onSuccess: (u) => {
      toast(t('{name} peut se connecter avec Jellyfin', { name: u.name }), 'success')
      refresh()
      qc.invalidateQueries({ queryKey: ['admin', 'jellyfin-accounts'] })
    },
    onError: (e) => toast(e.message, 'error'),
  })
  if (isLoading) return <Skeleton className="h-24" />
  if (error) return <p className="rounded-xl bg-bg3/60 p-3 text-sm text-text2">{error.message}</p>
  return (
    <ul className="divide-y divide-line">
      {(data?.results || []).map((a) => (
        <li key={a.id} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
          <Avatar user={{ name: a.name }} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{a.name}</p>
            <p className="truncate text-xs text-text3">
              {a.admin ? t('Administrateur du serveur') : t('Utilisateur du serveur')}
              {a.account_name ? ` · ${t('relié à {name}', { name: a.account_name })}` : ''}
            </p>
          </div>
          {a.account_id ? (
            <span className="flex items-center gap-1 text-xs font-medium text-emerald-500">
              <Check className="h-4 w-4" /> {t('Autorisé')}
            </span>
          ) : (
            <Button size="sm" onClick={() => allow.mutate(a)} loading={allow.isPending && allow.variables?.id === a.id}>
              {t('Autoriser')}
            </Button>
          )}
        </li>
      ))}
    </ul>
  )
}

export default function UsersPanel() {
  const t = useT()
  const { data: status } = useStatus()
  const me = useCurrentUser()
  const [adding, setAdding] = useState(false)
  const [resetting, setResetting] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const { data, isLoading } = useQuery({ queryKey: ['admin', 'users'], queryFn: admin.users })

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-line bg-bg2 p-4 md:p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="font-semibold">{t('Comptes SynCiné')}</h2>
          <Button size="sm" variant="primary" icon={Plus} onClick={() => setAdding(true)}>
            {t('Ajouter')}
          </Button>
        </div>
        {isLoading ? (
          <Skeleton className="h-24" />
        ) : (
          <ul className="divide-y divide-line">
            {(data?.results || []).map((u) => (
              <UserRow key={u.id} user={u} me={me} onReset={setResetting} onDelete={setDeleting} />
            ))}
          </ul>
        )}
        <p className="mt-4 text-xs text-text3">{t('Comptes locaux : tu choisis un identifiant et un mot de passe provisoire, que la personne change à sa première connexion.')}</p>
      </section>

      <section className="rounded-2xl border border-line bg-bg2 p-4 md:p-5">
        <h2 className="font-semibold">{t('Comptes Plex du serveur')}</h2>
        <p className="mb-4 mt-1 text-xs text-text2">{t('Les personnes avec qui ton serveur est partagé. Autorise celles qui peuvent se connecter à SynCiné avec leur compte Plex.')}</p>
        <PlexAccounts />
      </section>

      {status?.jellyfin?.server_linked && (
        <section className="rounded-2xl border border-line bg-bg2 p-4 md:p-5">
          <h2 className="font-semibold">{t('Comptes {server} du serveur', { server: status.jellyfin.kind === 'emby' ? 'Emby' : 'Jellyfin' })}</h2>
          <p className="mb-4 mt-1 text-xs text-text2">{t('Autorise les comptes qui peuvent se connecter à SynCiné avec leur identifiant Jellyfin ; leur mot de passe est vérifié par ton serveur.')}</p>
          <JellyfinAccounts />
        </section>
      )}

      <AddUserModal open={adding} onClose={() => setAdding(false)} />
      {resetting && <ResetPasswordModal user={resetting} onClose={() => setResetting(null)} />}
      {deleting && <DeleteModal user={deleting} onClose={() => setDeleting(null)} />}
    </div>
  )
}
