import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Clock, Film, Layers, Monitor, Moon, Plug, Plus, RotateCcw, Search, ShieldCheck, SlidersHorizontal, Sparkles, Sun, Tv, User } from 'lucide-react'
import ConnectionCard from '../components/profile/ConnectionCard'
import TraktConnect from '../components/profile/TraktConnect'
import JellyfinConnect from '../components/profile/JellyfinConnect'
import PlexConnect from '../components/profile/PlexConnect'
import SyncPanel from '../components/profile/SyncPanel'
import CinemaPicker from '../components/profile/CinemaPicker'
import RequestsPanel from '../components/profile/RequestsPanel'
import HiddenTitles from '../components/profile/HiddenTitles'
import { About, Support } from '../components/profile/About'
import NotificationSettings from '../components/profile/NotificationSettings'
import MenuOrder from '../components/profile/MenuOrder'
import DiscoverySettings from '../components/profile/DiscoverySettings'
import PlatformPicker from '../components/profile/PlatformPicker'
import Tabs from '../components/ui/Tabs'
import Button from '../components/ui/Button'
import Skeleton from '../components/ui/Skeleton'
import { SERVER_LABELS } from '../components/ui/PlatformBadge'
import { KID_LABELS } from '../lib/kids'
import { useCountries, useSettings, useStats, useStatus, useUpdateSettings } from '../hooks/useMedia'
import { useSettingsStore } from '../store/settingsStore'
import { swipe } from '../services/swipe'
import { useCurrentUser, usePersonal } from '../hooks/useAuth'
import { getAppPref, setAppPref } from '../lib/appLinks'
import { LANGUAGES } from '../lib/languages'
import { toast } from '../store/uiStore'
import { UI_LANGUAGES, fmtNumber, useT } from '../i18n'
import AccountSection from '../components/profile/AccountSection'
import AdminArea from '../components/profile/AdminArea'
import ProfileTabs from '../components/profile/ProfileTabs'
import Section, { SearchContext, fold } from '../components/profile/Section'
import ServerServices from '../components/profile/ServerServices'

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
  // Réglages du serveur : administrateur complet seulement (le principal, ou les autres s'il leur laisse l'accès)
  const serverAdmin = isAdmin && user?.server_admin !== false
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
  const shown = (k) => (serverAdmin || MEMBER_SERVICES.includes(k)) && (used[k] || added.includes(k))
  const hidden = Object.keys(SERVICE_META).filter((k) => !shown(k) && (serverAdmin || (MEMBER_SERVICES.includes(k) && (k !== 'trakt' || settings.trakt_client_id) && (k !== 'jellyfin' || status?.jellyfin?.server_linked))))
  // Seerr : demandes vers le serveur de la bibliothèque (Plex, Jellyfin ou Emby ; « ta bibliothèque » s'il y en a plusieurs)
  const serviceHint = (k) => {
    const both = status?.plex?.configured && status?.jellyfin?.configured
    if (k === 'seerr' && status?.media?.configured && !both) return t("Demandes d'ajout à {server}", { server: SERVER_LABELS[status.media.server] || 'Plex' })
    return t(SERVICE_META[k].hint)
  }
  const tr = stats?.watched // d'après tout l'historique gardé par SynCiné (toutes sources)
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

      {noTmdb && serverAdmin && (
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
              {!serverAdmin && <ServerServices user={user} status={status} />}
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
                fields={!serverAdmin ? [] : [
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
                <JellyfinConnect status={status?.jellyfin} isAdmin={serverAdmin} />
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

          {(serverAdmin || status?.media?.configured) && (
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
            <Section title={t('Partage')} keywords="partage share watchlist administrateur admin confidentialité privacy famille family goûts taste à deux">
              <div className="space-y-2">
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
              <label className="flex cursor-pointer items-start justify-between gap-4 rounded-2xl border border-line bg-bg2 px-4 py-3">
                <span className="min-w-0">
                  <span className="block text-sm font-medium">{t('Partager mes goûts avec la famille')}</span>
                  <span className="mt-0.5 block text-xs text-text2">
                    {t('Tes coups de cœur et tes bonnes notes servent aux suggestions « La famille a aimé » et « À deux » des membres qui partagent aussi les leurs ; « À deux » montre aussi les titres présents dans vos deux watchlists. Rien d’autre n’est visible.')}
                  </span>
                </span>
                <input
                  type="checkbox"
                  checked={!!settings.share_taste}
                  onChange={(e) => update.mutate({ share_taste: e.target.checked })}
                  className="mt-0.5 h-5 w-5 shrink-0 accent-[var(--accent)]"
                />
              </label>
              {user.is_admin && user.id === 1 && (
                <label className="flex cursor-pointer items-start justify-between gap-4 rounded-2xl border border-line bg-bg2 px-4 py-3">
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{t('Donner l’accès complet aux autres administrateurs')}</span>
                    <span className="mt-0.5 block text-xs text-text2">
                      {t('Tableau de bord et bibliothèque du serveur multimédia, réglages du serveur (TMDB, Plex, Jellyfin, Seerr…) et sauvegardes. Désactivé : les autres administrateurs gèrent seulement les comptes et les demandes.')}
                    </span>
                  </span>
                  <input
                    type="checkbox"
                    checked={!!settings.admins_full_access}
                    onChange={(e) => update.mutate({ admins_full_access: e.target.checked })}
                    className="mt-0.5 h-5 w-5 shrink-0 accent-[var(--accent)]"
                  />
                </label>
              )}
              </div>
            </Section>
          )}

          <Section
            title={t('Enfants du foyer')}
            keywords="enfants kids famille family âge age petits ados soirée"
            description={t('Leurs tranches d’âge : « Avec les enfants » dans Pour ce soir ne garde que ce qui convient au plus jeune, en titres familiaux.')}
          >
            <div className="flex flex-wrap gap-2">
              {Object.entries(KID_LABELS).map(([key, label]) => {
                const on = (settings.family_kids || []).includes(key)
                return (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={on}
                    onClick={() => update.mutate({ family_kids: on ? settings.family_kids.filter((k) => k !== key) : [...(settings.family_kids || []), key] })}
                    className={`rounded-full border px-3 py-1.5 text-sm transition ${on ? 'border-accent bg-accent/15 text-accent2' : 'border-line text-text2 hover:text-text'}`}
                  >
                    {t(label)}
                  </button>
                )
              })}
            </div>
          </Section>

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
