import { createContext, useContext, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, DatabaseBackup, Clock, Film, Inbox, KeyRound, Layers, LogOut, Monitor, Moon, Plug, Plus, RotateCcw, Search, Server, ShieldCheck, SlidersHorizontal, Sparkles, Sun, Tv, User, Users } from 'lucide-react'
import ConnectionCard from '../components/profile/ConnectionCard'
import TraktConnect from '../components/profile/TraktConnect'
import JellyfinConnect from '../components/profile/JellyfinConnect'
import PlexConnect from '../components/profile/PlexConnect'
import SyncPanel from '../components/profile/SyncPanel'
import CinemaPicker from '../components/profile/CinemaPicker'
import RequestsPanel from '../components/profile/RequestsPanel'
import ServerDashboard, { useMediaServers } from '../components/admin/ServerDashboard'
import UsersPanel from '../components/admin/UsersPanel'
import AdminRequests from '../components/admin/AdminRequests'
import BackupsPanel from '../components/admin/BackupsPanel'
import HiddenTitles from '../components/profile/HiddenTitles'
import TwoFactor from '../components/profile/TwoFactor'
import { About, Support } from '../components/profile/About'
import NotificationSettings from '../components/profile/NotificationSettings'
import MenuOrder from '../components/profile/MenuOrder'
import DiscoverySettings from '../components/profile/DiscoverySettings'
import PlatformPicker from '../components/profile/PlatformPicker'
import Tabs from '../components/ui/Tabs'
import Button from '../components/ui/Button'
import Skeleton from '../components/ui/Skeleton'
import { SERVER_LABELS } from '../components/ui/PlatformBadge'
import { useCountries, useSettings, useStats, useStatus, useUpdateSettings } from '../hooks/useMedia'
import { useSettingsStore } from '../store/settingsStore'
import { swipe } from '../services/swipe'
import { auth } from '../services/auth'
import { useCurrentUser, usePersonal, useResetSession } from '../hooks/useAuth'
import Modal from '../components/ui/Modal'
import { PasswordForm } from './Login'
import { getAppPref, setAppPref } from '../lib/appLinks'
import { LANGUAGES } from '../lib/languages'
import { toast } from '../store/uiStore'
import { UI_LANGUAGES, fmtNumber, useT } from '../i18n'

// Recherche dans les réglages : une rubrique s'affiche si son titre, sa description ou ses mots-clés
// (français et anglais) contiennent le texte cherché
const SearchContext = createContext('')
const fold = (s) => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()

function Section({ title, description, keywords = '', children, right, className = '' }) {
  const query = useContext(SearchContext)
  if (query && !fold(`${title} ${description || ''} ${keywords}`).includes(query)) return null
  return (
    <section className={`mb-10 ${className}`}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">{title}</h2>
        {right}
      </div>
      {description && <p className="mb-4 mt-0.5 text-sm text-text2">{description}</p>}
      {!description && <div className="mb-4" />}
      {children}
    </section>
  )
}

const SERVICE_META = {
  tmdb: { label: 'TMDB', color: '#01b4e4', hint: 'Indispensable : métadonnées et disponibilités' },
  plex: { label: 'Plex', color: 'var(--plex)', hint: 'Ta bibliothèque, lecture, historique' },
  jellyfin: { label: 'Jellyfin / Emby', color: '#aa5cc3', hint: 'Ta bibliothèque Jellyfin ou Emby, tes vus' },
  trakt: { label: 'Trakt', color: 'var(--trakt)', hint: 'Watchlist, historique, notes' },
  seerr: { label: 'Seerr', color: 'var(--seerr)', hint: "Demandes d'ajout à ta bibliothèque" },
  letterboxd: { label: 'Letterboxd', color: 'var(--letterboxd)', hint: 'Ton journal de films (RSS)' },
  justwatch: { label: 'JustWatch', color: 'var(--justwatch)', hint: 'Liens directs, top du jour, nouveautés' },
}


function Stat({ icon: Icon, label, value, sub }) {
  return (
    <div className="rounded-2xl border border-line bg-bg2 p-4">
      <Icon className="mb-3 h-5 w-5 text-accent2" />
      <p className="text-2xl font-semibold">{value ?? '–'}</p>
      <p className="text-xs text-text2">{label}</p>
      {sub && <p className="mt-0.5 text-[11px] text-text3">{sub}</p>}
    </div>
  )
}

// iPhone / iPad : oublier « toujours ouvrir l'app Plex / Netflix »
function AppPrefsReset() {
  const t = useT()
  const [apps, setApps] = useState(() => ['Plex', 'Netflix'].filter((a) => getAppPref(a)))
  if (!apps.length) return null
  return (
    <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-text2">
      {t('Ouverture directe dans l’app : {apps}', { apps: apps.join(', ') })}
      <Button
        size="sm"
        icon={RotateCcw}
        onClick={() => {
          apps.forEach((a) => setAppPref(a, null))
          setApps([])
          toast(t('Le choix app / navigateur sera de nouveau proposé'), 'success')
        }}
      >
        {t('Redemander')}
      </Button>
    </div>
  )
}

// Compte connecté : nom affiché, mot de passe, déconnexion
function AccountSection({ user }) {
  const t = useT()
  const personal = usePersonal()
  const reset = useResetSession()
  const [name, setName] = useState(user.display_name || '')
  const [pwOpen, setPwOpen] = useState(false)
  const [username, setUsername] = useState(user.username)
  const [removeOpen, setRemoveOpen] = useState(false)
  const [current, setCurrent] = useState('')
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

// Onglets du Profil : toujours sur une ligne ; sur téléphone, pictogramme au-dessus du libellé (colonnes égales)
function ProfileTabs({ value, onChange, options, className = '' }) {
  const t = useT()
  return (
    <div role="tablist" className={`grid w-full auto-cols-fr grid-flow-col gap-1 rounded-xl border border-line bg-bg2 p-1 sm:inline-grid sm:w-fit sm:auto-cols-auto ${className}`}>
      {options.map(({ value: v, label, icon: Icon }) => {
        const active = v === value
        return (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(v)}
            className={`flex min-w-0 flex-col items-center gap-0.5 rounded-lg px-1.5 py-1.5 text-[11px] font-medium transition sm:flex-row sm:gap-1.5 sm:px-4 sm:text-sm ${
              active ? 'bg-bg3 text-text shadow-sm' : 'text-text2 hover:text-text'
            }`}
          >
            <Icon className="h-4 w-4 shrink-0" />
            <span className="max-w-full truncate">{t(label)}</span>
          </button>
        )
      })}
    </div>
  )
}

// Onglet Admin du Profil : serveur(s) multimédia, comptes, demandes, sauvegardes, chacun dans un sous-onglet
function AdminArea({ section, onSection }) {
  const t = useT()
  const personal = usePersonal()
  const { data: servers = [] } = useMediaServers()
  // Libellé court : le nom du serveur (Plex, Jellyfin, Emby), ou « Serveurs » s'il y en a plusieurs
  const serverLabel = servers.length === 1 ? SERVER_LABELS[servers[0].kind] : servers.length > 1 ? 'Serveurs' : 'Serveur'
  const all = [
    { key: 'server', icon: Server, label: serverLabel, hint: 'Lectures en cours, débit, bibliothèques, statistiques', Panel: ServerDashboard },
    { key: 'users', icon: Users, label: 'Comptes', hint: 'Comptes locaux et comptes Plex, Jellyfin ou Emby autorisés', Panel: UsersPanel },
    { key: 'requests', icon: Inbox, label: 'Demandes', hint: 'Demandes d’ajout et watchlists partagées par la famille', Panel: AdminRequests },
    { key: 'backups', icon: DatabaseBackup, label: 'Sauvegardes', hint: 'Sauvegarde automatique de la base, téléchargement', Panel: BackupsPanel },
  ]
  const panels = personal ? all.filter((p) => p.key === 'server' || p.key === 'backups') : all
  // Recherche : la rubrique qui correspond s'affiche d'elle-même
  const query = useContext(SearchContext)
  const keywords = 'admin administration plex jellyfin emby serveur server dashboard comptes accounts famille family utilisateurs users demandes requests sauvegardes backups'
  const match = query ? panels.find((p) => fold(`${t(p.label)} ${t(p.hint)}`).includes(query)) : null
  if (query && !match && !fold(keywords).includes(query)) return null
  const current = match || panels.find((p) => p.key === section) || panels[0]
  const { Panel } = current
  return (
    <section className="mb-10">
      {query && <h2 className="mb-4 text-lg font-semibold">{t('Réglages admin')}</h2>}
      {panels.length > 1 && (
        <ProfileTabs value={current.key} onChange={onSection} options={panels.map(({ key, label, icon }) => ({ value: key, label, icon }))} />
      )}
      <p className="mb-4 mt-3 text-sm text-text2">
        {t(current.hint)}
        {current.key === 'server' && !personal && ` · ${t('Les connexions TMDB, serveur multimédia (Plex, Jellyfin, Emby), Seerr et JustWatch sont partagées par tous les comptes.')}`}
      </p>
      <Panel />
    </section>
  )
}

// Membre : services fournis par le serveur (réglés par l'administrateur, rien à configurer de son côté)
function ServerServices({ user, status }) {
  const t = useT()
  const rows = [
    { key: 'tmdb', color: '#01b4e4', label: 'TMDB', on: status?.tmdb?.configured, desc: t('Fiches, tendances, sorties et disponibilités streaming') },
    { key: 'justwatch', color: 'var(--justwatch)', label: 'JustWatch', on: status?.justwatch?.configured, desc: t('Liens directs vers chaque plateforme et nouveautés') },
    status?.plex?.configured && {
      key: 'plex',
      color: 'var(--plex)',
      label: 'Plex',
      on: true,
      desc: user.plex
        ? t('Compte {name} · serveur {server}', { name: user.plex.username, server: status?.plex?.server || '—' })
        : t('Serveur {server}, partagé par l’administrateur', { server: status?.plex?.server || '—' }),
      note: !status?.plex?.own && t('Connecte-toi avec Plex pour synchroniser tes propres vus et ta progression.'),
    },
    status?.jellyfin?.configured && !status?.plex?.configured && {
      key: 'jellyfin',
      color: '#aa5cc3',
      label: SERVER_LABELS[status.jellyfin.kind] || 'Jellyfin',
      on: true,
      desc: status.jellyfin.linked
        ? t('Compte {name} · serveur {server}', { name: status.jellyfin.username, server: status.jellyfin.server || '—' })
        : t('Serveur {server}, partagé par l’administrateur', { server: status.jellyfin.server || '—' }),
    },
    // Demandes d'ajout au serveur multimédia : seulement pour les comptes qui y sont reliés
    status?.seerr?.configured && status?.media?.configured && {
      key: 'seerr',
      color: 'var(--seerr)',
      label: 'Seerr',
      on: true,
      desc: user.can_request_direct ? t('Tes demandes d’ajout partent directement à Seerr') : t('Tes demandes d’ajout passent par l’administrateur'),
    },
  ].filter(Boolean)
  return (
    <div className="rounded-2xl border border-line bg-bg2 p-4">
      <p className="font-medium">{t('Fournis par le serveur')}</p>
      <p className="mt-0.5 text-xs text-text2">{t('Réglés par l’administrateur pour tout le monde : déjà actifs pour toi, rien à configurer.')}</p>
      <ul className="mt-3 divide-y divide-line">
        {rows.map((r) => (
          <li key={r.key} className="flex items-start gap-3 py-2.5 last:pb-0">
            <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-semibold text-white" style={{ background: r.color }}>
              {r.label[0]}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">{r.label}</p>
              <p className="text-xs text-text2">{r.desc}</p>
              {r.note && <p className="mt-0.5 text-xs text-text3">{r.note}</p>}
            </div>
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${r.on ? 'bg-emerald-500/15 text-emerald-500' : 'bg-bg3 text-text3'}`}>
              {r.on ? t('Actif') : t('Non activé')}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function Profile() {
  const t = useT()
  const { data: settings, isLoading } = useSettings()
  const [added, setAdded] = useState([])
  const [addOpen, setAddOpen] = useState(false)
  const { data: status } = useStatus()
  const { data: stats } = useStats()
  const { data: countries } = useCountries()
  const update = useUpdateSettings()
  const setTheme = useSettingsStore((s) => s.setTheme)
  const uiLanguage = useSettingsStore((s) => s.uiLanguage)
  const setUiLanguage = useSettingsStore((s) => s.setUiLanguage)
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const user = useCurrentUser()
  const isAdmin = !!user?.is_admin
  const personal = usePersonal()
  const [search, setSearch] = useState('')
  const query = fold(search.trim())
  // Sous-onglets du Profil (dans l'adresse : /profile?tab=admin&section=requests) ; une recherche parcourt tous les onglets
  const tabs = [
    { value: 'account', label: 'Compte', icon: User },
    { value: 'connections', label: 'Connexions', icon: Plug },
    { value: 'prefs', label: 'Préférences', icon: SlidersHorizontal },
    isAdmin && { value: 'admin', label: 'Admin', icon: ShieldCheck },
  ].filter(Boolean)
  const tab = tabs.some((x) => x.value === params.get('tab')) ? params.get('tab') : 'account'
  const show = (group) => !!query || tab === group
  const goTab = (value) => {
    setParams({ tab: value }, { replace: true })
    window.scrollTo({ top: 0 })
  }

  // Retour du flux OAuth Trakt
  useEffect(() => {
    const result = params.get('trakt')
    if (!result) return
    if (result === 'connected') {
      toast(t('Trakt connecté !'), 'success')
      qc.invalidateQueries()
    } else {
      const reasons = { state: 'jeton de sécurité invalide, réessaie', token: 'échange du code refusé — vérifie client ID, secret et URL de retour' }
      const reason = params.get('reason')
      toast(t('Connexion Trakt échouée : {reason}', { reason: reasons[reason] ? t(reasons[reason]) : reason || t('erreur inconnue') }), 'error')
    }
    setParams({ tab: 'connections' }, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const resetSkips = useMutation({
    mutationFn: () => swipe.reset('skip'),
    onSuccess: (r) =>
      toast(
        r.deleted > 1
          ? t('{n} titres passés pourront être reproposés', { n: r.deleted })
          : t('{n} titre passé pourra être reproposé', { n: r.deleted }),
        'success',
      ),
  })

  const changeTheme = (theme) => {
    setTheme(theme)
    update.mutate({ theme })
  }

  const changeUiLanguage = (code) => {
    setUiLanguage(code)
    update.mutate({ ui_language: code })
  }

  if (isLoading || !settings) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48" />
        <Skeleton className="h-48" />
      </div>
    )
  }

  const used = {
    tmdb: true, // toujours affiché : indispensable
    plex: !!(status?.plex?.configured || settings.plex_account_connected),
    jellyfin: !!status?.jellyfin?.server_linked,
    trakt: !!settings.trakt_client_id,
    seerr: !!status?.seerr?.configured,
    letterboxd: !!status?.letterboxd?.configured,
    justwatch: !!settings.justwatch_enabled,
  }
  // Un membre ne règle que ses services personnels ; le reste appartient à l'administrateur
  const MEMBER_SERVICES = ['trakt', 'letterboxd', 'jellyfin']
  const shown = (k) => (isAdmin || MEMBER_SERVICES.includes(k)) && (used[k] || added.includes(k))
  const hidden = Object.keys(SERVICE_META).filter((k) => !shown(k) && (isAdmin || (MEMBER_SERVICES.includes(k) && (k !== 'trakt' || settings.trakt_client_id) && (k !== 'jellyfin' || status?.jellyfin?.server_linked))))
  // Seerr : demandes vers le serveur de la bibliothèque (Plex, Jellyfin ou Emby ; « ta bibliothèque » s'il y en a plusieurs)
  const serviceHint = (k) => {
    const both = status?.plex?.configured && status?.jellyfin?.configured
    if (k === 'seerr' && status?.media?.configured && !both) return t("Demandes d'ajout à {server}", { server: SERVER_LABELS[status.media.server] || 'Plex' })
    return t(SERVICE_META[k].hint)
  }
  const tr = stats?.trakt
  const p = stats?.plex
  const noTmdb = !status?.tmdb?.configured

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-1 text-2xl font-semibold md:text-3xl">{t('Profil et paramètres')}</h1>
      <p className="mb-5 text-sm text-text2">{t('Connecte tes services : tout le reste de SynCiné en dépend.')}</p>

      <div className="relative mb-8">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text3" />
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t('Rechercher un réglage…')}
          aria-label={t('Rechercher un réglage')}
          className="h-11 w-full rounded-xl border border-line bg-bg2 pl-9 pr-3 text-sm outline-none placeholder:text-text3 focus:border-accent"
        />
      </div>

      {!query && <ProfileTabs className="mb-8" value={tab} onChange={goTab} options={tabs} />}

      {noTmdb && isAdmin && (
        <div className="mb-8 flex gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm">
          <AlertTriangle className="h-5 w-5 shrink-0 text-amber-500" />
          <div>
            <p className="font-medium">{t('Commence par TMDB')}</p>
            <p className="mt-0.5 text-text2">
              {t('Sans clé TMDB, SynCiné affiche des données de démonstration. La clé est gratuite : crée un compte sur themoviedb.org, puis Paramètres → API.')}
            </p>
            {tab !== 'connections' && !query && (
              <button type="button" onClick={() => goTab('connections')} className="mt-2 font-medium text-accent2 hover:underline">
                {t('Aller aux connexions')}
              </button>
            )}
          </div>
        </div>
      )}

      <SearchContext.Provider value={query}>
      {show('account') && (
        <>
          {!query && (
            <div className="mb-10">
              <Support />
            </div>
          )}
          {user && <AccountSection user={user} />}
          <Section title={t('Notifications')} keywords="notifications alertes alerts cloche bell push téléphone phone appareil device épisodes disponibilités pannes" description={t("Choisis ce qui s'affiche sous la cloche.")}>
            <NotificationSettings settings={settings} />
          </Section>
          <Section title={t('Statistiques')} keywords="statistiques stats heures hours films séries" description={t('Aperçu — le détail par jour, semaine, mois et année est dans la page Statistiques.')}>
            <Link to="/stats" className="mb-4 inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-medium text-white transition hover:-translate-y-0.5 hover:brightness-110">
              {t('Voir toutes les statistiques')}
            </Link>
            <div className={`grid grid-cols-2 gap-3 ${p ? 'sm:grid-cols-4' : 'sm:grid-cols-3'}`}>
              <Stat icon={Film} label={t('Films vus')} value={tr?.movies_watched} />
              <Stat icon={Tv} label={t('Séries suivies')} value={tr?.shows_watched} sub={tr ? t('{n} épisodes', { n: fmtNumber(tr.episodes_watched) }) : null} />
              <Stat icon={Clock} label={t('Heures de visionnage')} value={tr?.hours != null ? fmtNumber(tr.hours) : undefined} />
              {p && (
                <Stat
                  icon={Layers}
                  label={t('Bibliothèque {server}', { server: SERVER_LABELS[p.server] || 'Plex' })}
                  value={p ? p.movies + p.shows : null}
                  sub={p ? t('{movies} films · {shows} séries', { movies: p.movies, shows: p.shows }) : null}
                />
              )}
            </div>
          </Section>
          <Section title={t('À propos')} keywords="à propos about version licence license crédits credits contributeurs ko-fi soutenir support">
            <About />
          </Section>
        </>
      )}

      {show('connections') && (
        <>

          <Section
            title={t('Connexions')}
            keywords="connexions connections services tmdb plex trakt seerr letterboxd justwatch clé key api token serveur server"
            description={t("Les services que tu utilises. Ajoute-en d'autres avec le bouton +.")}
            right={
              hidden.length > 0 && (
                <div className="relative">
                  <Button size="icon" variant="primary" onClick={() => setAddOpen((o) => !o)} aria-label={t('Ajouter un service')} title={t('Ajouter un service')}>
                    <Plus className="h-5 w-5" />
                  </Button>
                  {addOpen && (
                    <div className="absolute right-0 top-12 z-20 w-72 overflow-hidden rounded-2xl border border-line bg-bg2 shadow-2xl">
                      {hidden.map((k) => (
                        <button
                          key={k}
                          onClick={() => {
                            setAdded((a) => [...a, k])
                            setAddOpen(false)
                          }}
                          className="flex w-full items-start gap-3 border-b border-line px-4 py-3 text-left last:border-none hover:bg-bg3"
                        >
                          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-semibold text-white" style={{ background: SERVICE_META[k].color }}>
                            {SERVICE_META[k].label[0]}
                          </span>
                          <span>
                            <span className="block text-sm font-medium">{SERVICE_META[k].label}</span>
                            <span className="block text-xs text-text2">{serviceHint(k)}</span>
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )
            }
          >
            <div className="grid grid-cols-1 gap-4">
              {!isAdmin && <ServerServices user={user} status={status} />}
              {shown('tmdb') && (
              <ConnectionCard
                service="tmdb"
                title="TMDB"
                color="#01b4e4"
                description="Métadonnées, tendances, sorties et disponibilités streaming"
                helpUrl="https://www.themoviedb.org/settings/api"
                helpLabel="Obtenir une clé"
                settings={settings}
                connected={status?.tmdb?.configured}
                fields={[{ name: 'tmdb_api_key', label: 'Clé API (v3) ou jeton de lecture (v4)', secret: true, placeholder: 'ex. 3f2a…' }]}
              />
              )}

              {shown('plex') && (
              <ConnectionCard
                service="plex"
                title="Plex"
                color="var(--plex)"
                description="Ta bibliothèque personnelle"
                helpUrl="https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/"
                helpLabel="Trouver mon token"
                settings={settings}
                connected={status?.plex?.configured}
                manualLabel="Saisie manuelle (URL du serveur + token)"
                fields={[
                  { name: 'plex_url', label: 'URL du serveur', placeholder: 'http://ip-du-serveur:32400', hint: 'Adresse du serveur Plex vue depuis le backend (IP locale, pas localhost en Docker)' },
                  { name: 'plex_token', label: 'Token (X-Plex-Token)', secret: true, placeholder: 'xxxxxxxxxxxxxxxxxxxx' },
                ]}
              >
                <PlexConnect settings={settings} />
              </ConnectionCard>
              )}

              {shown('trakt') && (
              <ConnectionCard
                service="trakt"
                title="Trakt"
                color="var(--trakt)"
                description="Watchlist, historique, notes et recommandations"
                helpUrl="https://trakt.tv/oauth/applications/new"
                helpLabel="Créer une application"
                settings={settings}
                connected={status?.trakt?.connected}
                fields={!isAdmin ? [] : [
                  {
                    name: 'trakt_client_id',
                    label: 'Client ID',
                    placeholder: 'Client ID de ton application Trakt',
                    hint: 'Aucun client secret nécessaire. Dans l’appli Trakt, l’URL de retour peut rester urn:ietf:wg:oauth:2.0:oob.',
                  },
                ]}
              >
                <TraktConnect settings={settings} />
              </ConnectionCard>
              )}

              {shown('jellyfin') && (
              <ConnectionCard
                service="jellyfin"
                title={status?.jellyfin?.kind === 'emby' ? 'Emby' : 'Jellyfin'}
                color="#aa5cc3"
                description="Ta bibliothèque Jellyfin ou Emby, tes vus et ta progression"
                settings={settings}
                connected={status?.jellyfin?.configured}
                optional
                testable={!!status?.jellyfin?.server_linked}
              >
                <JellyfinConnect status={status?.jellyfin} isAdmin={isAdmin} />
              </ConnectionCard>
              )}

              {shown('seerr') && (
              <ConnectionCard
                service="seerr"
                title="Seerr"
                color="var(--seerr)"
                description="Envoyer une demande de film ou série (tu valides dans Seerr)"
                settings={settings}
                connected={status?.seerr?.configured}
                optional
                fields={[
                  { name: 'seerr_url', label: 'URL de Seerr', placeholder: 'http://ip-du-serveur:5055' },
                  { name: 'seerr_api_key', label: 'Clé API', secret: true, placeholder: 'Paramètres → Général → Clé API', hint: 'Dans Seerr : Paramètres → Général → Clé API' },
                ]}
              />
              )}

              {shown('letterboxd') && (
              <ConnectionCard
                service="letterboxd"
                title="Letterboxd"
                color="var(--letterboxd)"
                description="Tes derniers films vus, via ton flux RSS public"
                settings={settings}
                connected={status?.letterboxd?.configured}
                optional
                fields={[{ name: 'letterboxd_username', label: "Nom d'utilisateur", placeholder: 'ton-pseudo' }]}
              />
              )}

              {shown('justwatch') && (
              <ConnectionCard
                service="justwatch"
                title="JustWatch"
                color="var(--justwatch)"
                description="Liens directs vers chaque plateforme et nouveautés de la semaine"
                settings={settings}
                connected={settings.justwatch_enabled}
                optional
                testable={settings.justwatch_enabled}
              >
                <div className="flex items-start gap-3 rounded-xl bg-bg3 p-3 text-xs text-text2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />
                  <span>
                    {t(
                      "Utilise l'API interne non officielle de JustWatch : elle peut cesser de fonctionner sans prévenir. Dans ce cas, SynCiné revient automatiquement aux données TMDB (qui proviennent aussi de JustWatch, mais sans liens directs).",
                    )}
                  </span>
                </div>
                <label className="mt-3 flex cursor-pointer items-center justify-between rounded-xl border border-line bg-bg px-3 py-3">
                  <span className="text-sm">{t('Activer JustWatch')}</span>
                  <input
                    type="checkbox"
                    checked={settings.justwatch_enabled}
                    onChange={(e) => update.mutate({ justwatch_enabled: e.target.checked })}
                    className="h-5 w-5 accent-[var(--accent)]"
                  />
                </label>
              </ConnectionCard>
              )}
            </div>
          </Section>

          <Section title={t('Synchronisation')} keywords="sync synchro trakt plex letterboxd watchlist vus watched notes ratings" description={t('Watchlist, titres vus, notes et coups de cœur, réunis depuis Trakt, Plex et Letterboxd, et sauvegardés dans SynCiné.')}>
            <SyncPanel />
          </Section>

          {(isAdmin || status?.media?.configured) && (
            <Section title={t('Mes demandes')} keywords="demandes requests seerr plex jellyfin emby ajout" description={t('Titres que tu as demandés pour ta bibliothèque.')}>
              <RequestsPanel />
            </Section>
          )}
        </>
      )}

      {show('prefs') && (
        <>
          <Section title={t('Région & Langue')} keywords="pays country langue language interface anglais english français region" description={t('Le pays détermine les disponibilités et sorties affichées ; la langue des contenus, celle des titres et résumés.')}>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-text2">{t('Pays')}</span>
                <select
                  value={settings.country_code}
                  onChange={(e) => update.mutate({ country_code: e.target.value })}
                  className="h-11 w-full rounded-xl border border-line bg-bg2 px-3 text-sm outline-none focus:border-accent"
                >
                  {(countries || [{ code: settings.country_code, name: settings.country_code }]).map((c) => (
                    <option key={c.code} value={c.code}>
                      {c.name} ({c.code})
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-text2">{t('Langue des contenus')}</span>
                <select
                  value={settings.language}
                  onChange={(e) => update.mutate({ language: e.target.value })}
                  className="h-11 w-full rounded-xl border border-line bg-bg2 px-3 text-sm outline-none focus:border-accent"
                >
                  {LANGUAGES.map(([code, name]) => (
                    <option key={code} value={code}>
                      {name}
                    </option>
                  ))}
                </select>
                <span className="mt-1 block text-xs text-text3">{t('Titres, résumés et bandes-annonces.')}</span>
              </label>
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-text2">{t("Langue de l'interface")}</span>
                <select
                  value={uiLanguage}
                  onChange={(e) => changeUiLanguage(e.target.value)}
                  className="h-11 w-full rounded-xl border border-line bg-bg2 px-3 text-sm outline-none focus:border-accent"
                >
                  {UI_LANGUAGES.map((l) => (
                    <option key={l.code} value={l.code}>
                      {l.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </Section>

          <Section title={t('Plateformes')} keywords="plateformes platforms abonnements subscriptions streaming netflix disney prime canal" description={t('Coche les plateformes auxquelles tu es abonné : badges, filtres, bouton « Regarder sur… » et notifications.')}>
            <PlatformPicker settings={settings} />
          </Section>

          <Section title={t('Cinémas')} keywords="cinémas cinemas salles séances showtimes allociné" description={t('Tes salles habituelles : leurs séances apparaissent dans « À venir » → Sorties cinéma et dans Découvrir.')}>
            <CinemaPicker settings={settings} />
          </Section>

          <Section title={t('Découverte')} keywords="découverte discover suggestions recommandations vus seen sorties releases watchlist" description={t('Ce que SynCiné te propose dans Découvrir et dans les recommandations des fiches.')}>
            <DiscoverySettings settings={settings} />
          </Section>

          {!personal && (
            <Section title={t('Partage avec l’administrateur')} keywords="partage share watchlist administrateur admin confidentialité privacy">
              <label className="flex cursor-pointer items-start justify-between gap-4 rounded-2xl border border-line bg-bg2 px-4 py-3">
                <span className="min-w-0">
                  <span className="block text-sm font-medium">{t('Montrer ma watchlist à l’administrateur')}</span>
                  <span className="mt-0.5 block text-xs text-text2">
                    {t('Seulement les titres que tu ne peux regarder ni sur tes plateformes, ni dans la bibliothèque : l’administrateur sait ainsi quoi ajouter. Rien d’autre (vus, notes…) n’est partagé.')}
                  </span>
                </span>
                <input
                  type="checkbox"
                  checked={!!settings.share_watchlist}
                  onChange={(e) => update.mutate({ share_watchlist: e.target.checked })}
                  className="mt-0.5 h-5 w-5 shrink-0 accent-[var(--accent)]"
                />
              </label>
            </Section>
          )}

          <Section title={t('Apparence')} keywords="apparence appearance thème theme sombre dark clair light assistant démarrage setup app plex netflix">
            <Tabs
              value={settings.theme}
              onChange={changeTheme}
              options={[
                { value: 'auto', label: 'Auto', icon: Monitor },
                { value: 'light', label: 'Clair', icon: Sun },
                { value: 'dark', label: 'Sombre', icon: Moon },
              ]}
            />
            <AppPrefsReset />
            <Link to="/welcome" className="mt-4 inline-flex items-center gap-1.5 text-sm text-accent2 hover:underline">
              <Sparkles className="h-4 w-4" /> {t('Revoir l’assistant de démarrage')}
            </Link>
          </Section>

          <Section title={t('Titres masqués')} keywords="masqués hidden pas intéressé not interested" description={t("Marqués « pas intéressé » : ils n'apparaissent plus dans tes suggestions (ni dans tes recommandations Trakt).")}>
            <HiddenTitles />
          </Section>

          <Section title={t('Mode swipe')} keywords="swipe passés skipped réinitialiser reset" description={t('Les titres passés (✕) ne sont jamais reproposés. Tu peux remettre ce compteur à zéro.')}>
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm text-text2">
                {t('{skip} passé(s) · {like} aimé(s) · {seen} déjà vu(s)', { skip: stats?.swipe?.skip || 0, like: stats?.swipe?.like || 0, seen: stats?.swipe?.seen || 0 })}
              </span>
              <Button size="sm" icon={RotateCcw} onClick={() => resetSkips.mutate()} loading={resetSkips.isPending}>
                {t('Réinitialiser les titres passés')}
              </Button>
            </div>
          </Section>

          <Section
            className="hidden lg:block"
            title={t('Menu (version ordinateur)')}
            description={t('Range les onglets du menu de gauche dans l’ordre qui te convient.')}
            keywords="menu onglets tabs ordre order barre latérale sidebar navigation"
          >
            <MenuOrder settings={settings} />
          </Section>
        </>
      )}

      {isAdmin && show('admin') && <AdminArea section={params.get('section')} onSection={(v) => setParams({ tab: 'admin', section: v }, { replace: true })} />}

      {query && <p className="py-10 text-center text-sm text-text3 only:block">{t('Aucun autre réglage ne correspond à « {q} ».', { q: search })}</p>}
      </SearchContext.Provider>
    </div>
  )
}
