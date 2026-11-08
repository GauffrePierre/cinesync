import { useState } from 'react'
import { useNavigate } from 'react-router'
import { ArrowLeft, ArrowRight, Check, Layers, Sparkles } from 'lucide-react'
import Logo from '../components/layout/Logo'
import Button from '../components/ui/Button'
import ConnectionCard from '../components/profile/ConnectionCard'
import PlatformPicker from '../components/profile/PlatformPicker'
import CinemaPicker from '../components/profile/CinemaPicker'
import TraktConnect from '../components/profile/TraktConnect'
import PlexConnect from '../components/profile/PlexConnect'
import PushSettings from '../components/profile/PushSettings'
import { useCountries, useSettings, useStatus, useUpdateSettings } from '../hooks/useMedia'
import { useCurrentUser, usePersonal } from '../hooks/useAuth'
import { useSettingsStore } from '../store/settingsStore'
import { LANGUAGES } from '../lib/languages'
import { UI_LANGUAGES, useT } from '../i18n'

// Assistant de premier démarrage : quelques écrans pour que SynCiné soit utile tout de suite.
// Chaque étape enregistre aussitôt (mêmes composants que le Profil) ; tout reste modifiable ensuite.

const select = 'h-11 w-full rounded-xl border border-line bg-bg2 px-3 text-sm outline-none focus:border-accent'

function Region({ settings }) {
  const t = useT()
  const update = useUpdateSettings()
  const { data: countries } = useCountries()
  const uiLanguage = useSettingsStore((s) => s.uiLanguage)
  const setUiLanguage = useSettingsStore((s) => s.setUiLanguage)
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="block sm:col-span-2">
        <span className="mb-1.5 block text-xs font-medium text-text2">{t("Langue de l'interface")}</span>
        <select
          value={uiLanguage}
          onChange={(e) => {
            setUiLanguage(e.target.value)
            update.mutate({ ui_language: e.target.value })
          }}
          className={select}
        >
          {UI_LANGUAGES.map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="mb-1.5 block text-xs font-medium text-text2">{t('Pays')}</span>
        <select value={settings.country_code} onChange={(e) => update.mutate({ country_code: e.target.value })} className={select}>
          {(countries || [{ code: settings.country_code, name: settings.country_code }]).map((c) => (
            <option key={c.code} value={c.code}>
              {c.name} ({c.code})
            </option>
          ))}
        </select>
        <span className="mt-1 block text-xs text-text3">{t('Disponibilités en streaming et sorties de ce pays.')}</span>
      </label>
      <label className="block">
        <span className="mb-1.5 block text-xs font-medium text-text2">{t('Langue des contenus')}</span>
        <select value={settings.language} onChange={(e) => update.mutate({ language: e.target.value })} className={select}>
          {LANGUAGES.map(([code, name]) => (
            <option key={code} value={code}>
              {name}
            </option>
          ))}
        </select>
        <span className="mt-1 block text-xs text-text3">{t('Titres, résumés et bandes-annonces.')}</span>
      </label>
    </div>
  )
}

function Services({ settings, status, isAdmin }) {
  return (
    <div className="space-y-4">
      {isAdmin && (
        <ConnectionCard
          service="plex"
          title="Plex"
          color="var(--plex)"
          description="Ta bibliothèque personnelle"
          settings={settings}
          connected={status?.plex?.configured}
          optional
          manualLabel="Saisie manuelle (URL du serveur + token)"
          fields={[
            { name: 'plex_url', label: 'URL du serveur', placeholder: 'http://ip-du-serveur:32400' },
            { name: 'plex_token', label: 'Token (X-Plex-Token)', secret: true },
          ]}
        >
          <PlexConnect settings={settings} />
        </ConnectionCard>
      )}
      {(isAdmin || status?.trakt?.configured) && (
        <ConnectionCard
          service="trakt"
          title="Trakt"
          color="var(--trakt)"
          description="Watchlist, historique, notes et recommandations"
          helpUrl={isAdmin ? 'https://trakt.tv/oauth/applications/new' : undefined}
          helpLabel={isAdmin ? 'Créer une application' : undefined}
          settings={settings}
          connected={status?.trakt?.connected}
          optional
          fields={isAdmin ? [{ name: 'trakt_client_id', label: 'Client ID', placeholder: 'Client ID de ton application Trakt' }] : []}
        >
          <TraktConnect settings={settings} />
        </ConnectionCard>
      )}
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
    </div>
  )
}

export default function Onboarding() {
  const t = useT()
  const navigate = useNavigate()
  const user = useCurrentUser()
  const personal = usePersonal()
  const { data: settings } = useSettings()
  const { data: status } = useStatus()
  const update = useUpdateSettings()
  const [index, setIndex] = useState(0)
  const isAdmin = !!user?.is_admin

  if (!settings) return null

  const steps = [
    {
      key: 'welcome',
      title: t('Bienvenue sur SynCiné, {name} !', { name: user?.name || '' }),
      intro: t('Quelques réglages et SynCiné te montre ce que tu peux regarder ce soir, où, et ce qui sort au cinéma près de chez toi. Tout reste modifiable dans le Profil.'),
      body: <Region settings={settings} />,
    },
    isAdmin && !status?.tmdb?.configured && {
      key: 'tmdb',
      title: t('La clé TMDB'),
      intro: t('TMDB fournit les fiches, affiches, tendances et sorties. La clé est gratuite : crée un compte sur themoviedb.org, puis Paramètres → API.'),
      body: (
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
      ),
    },
    {
      key: 'platforms',
      title: t('Tes plateformes'),
      intro: t('Coche tes abonnements : SynCiné te signale ce qui y est disponible et te prévient quand un titre de ta watchlist y arrive.'),
      body: <PlatformPicker settings={settings} />,
    },
    {
      key: 'cinemas',
      title: t('Tes cinémas'),
      intro: t('Tes salles habituelles : leurs séances apparaissent dans « À venir » et dans Découvrir. Facultatif.'),
      body: <CinemaPicker settings={settings} />,
    },
    {
      key: 'services',
      title: t('Tes comptes'),
      intro: isAdmin
        ? t('Relie ton serveur Plex et tes comptes : watchlist, vus et notes sont réunis et synchronisés. Tout est facultatif.')
        : t('Relie tes comptes : watchlist, vus et notes sont réunis et synchronisés. Tout est facultatif.'),
      body: <Services settings={settings} status={status} isAdmin={isAdmin} />,
    },
    {
      key: 'notifications',
      title: t('Les notifications'),
      intro: t('Nouvel épisode, titre de ta watchlist disponible, service en panne : reçois-les aussi sur cet appareil.'),
      body: <PushSettings />,
    },
    {
      key: 'done',
      title: t('C’est prêt !'),
      intro: personal
        ? t('Découvre ce qui est disponible pour toi. Pense à protéger l’accès par un mot de passe dans le Profil si SynCiné est accessible hors de chez toi.')
        : t('Découvre ce qui est disponible pour toi.'),
      body: (
        <div className="flex items-start gap-3 rounded-2xl tint-accent border border-line p-4 text-sm text-text2">
          <Layers className="mt-0.5 h-5 w-5 shrink-0 text-accent2" />
          {t('Astuce : le mode swipe (un titre à la fois, passe / ajoute / aime) affine très vite tes suggestions.')}
        </div>
      ),
    },
  ].filter(Boolean)

  const step = steps[Math.min(index, steps.length - 1)]
  const last = index >= steps.length - 1
  const finish = (to = '/') => {
    update.mutate({ onboarding: 'done' }, { onSuccess: () => navigate(to, { replace: true }) })
  }

  return (
    <div className="flex min-h-dvh flex-col bg-bg text-text">
      <header className="mx-auto flex w-full max-w-2xl items-center justify-between px-4 pt-6">
        <Logo />
        {!last && (
          <button onClick={() => finish()} className="text-xs text-text3 hover:text-text2">
            {t('Passer l’assistant')}
          </button>
        )}
      </header>
      <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-8">
        <div className="mb-6 flex gap-1.5" aria-label={t('Étape {n} sur {total}', { n: index + 1, total: steps.length })}>
          {steps.map((s, i) => (
            <span key={s.key} className={`h-1.5 flex-1 rounded-full transition ${i <= index ? 'bg-accent' : 'bg-bg3'}`} />
          ))}
        </div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold md:text-3xl">
          {last && <Sparkles className="h-6 w-6 text-accent2" />}
          {step.title}
        </h1>
        <p className="mt-2 text-sm text-text2">{step.intro}</p>
        <div className="mt-6">{step.body}</div>
      </main>
      <footer className="sticky bottom-0 border-t border-line bg-bg/95 backdrop-blur pb-[env(safe-area-inset-bottom)]">
        <div className="mx-auto flex w-full max-w-2xl items-center justify-between gap-3 px-4 py-3">
          <Button variant="ghost" icon={ArrowLeft} onClick={() => setIndex((i) => i - 1)} disabled={index === 0}>
            {t('Retour')}
          </Button>
          <span className="text-xs text-text3">{t('Étape {n} sur {total}', { n: index + 1, total: steps.length })}</span>
          {last ? (
            <Button variant="primary" icon={Check} onClick={() => finish()} loading={update.isPending}>
              {t('Découvrir')}
            </Button>
          ) : (
            <Button variant="primary" onClick={() => setIndex((i) => i + 1)}>
              {t('Suivant')} <ArrowRight className="h-4 w-4" />
            </Button>
          )}
        </div>
      </footer>
    </div>
  )
}
