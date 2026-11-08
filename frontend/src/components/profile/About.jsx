import { useQuery } from '@tanstack/react-query'
import { Cat, Coffee, Github, Heart, Scale, ShieldCheck } from 'lucide-react'
import { api } from '../../services/api'
import { PROJECT } from '../../lib/project'
import { useT } from '../../i18n'

const link = 'inline-flex items-center gap-1 text-accent2 hover:underline'

// « Un café pour moi, des croquettes pour Claude » : soutenir le projet (Ko-fi)
export function Support() {
  const t = useT()
  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-amber-500/30 bg-amber-500/5 p-5 sm:flex-row sm:items-center">
      <div className="flex shrink-0 gap-1 text-amber-500">
        <Coffee className="h-7 w-7" />
        <Cat className="h-7 w-7" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-medium">{t('Un café pour moi, des croquettes pour Claude')}</p>
        <p className="mt-1 text-sm text-text2">
          {t('SynCiné est gratuit, libre et sans publicité. Si l’appli te plaît, tu peux offrir un café au développeur… et des croquettes à Claude, son chat.')}
        </p>
      </div>
      {PROJECT.supportUrl ? (
        <a
          href={PROJECT.supportUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-amber-500 px-4 py-2.5 text-sm font-semibold text-black transition hover:brightness-110"
        >
          <Heart className="h-4 w-4" /> {t('Soutenir SynCiné')}
        </a>
      ) : (
        <span className="shrink-0 rounded-xl border border-dashed border-amber-500/40 px-4 py-2.5 text-center text-xs text-text2">{t('Lien de soutien bientôt disponible')}</span>
      )}
    </div>
  )
}

function Row({ label, children }) {
  return (
    <div className="flex flex-col gap-0.5 py-3 sm:flex-row sm:gap-4">
      <dt className="w-36 shrink-0 text-xs font-medium uppercase tracking-wide text-text3">{label}</dt>
      <dd className="min-w-0 flex-1 text-sm text-text2">{children}</dd>
    </div>
  )
}

// Crédits, contributeurs, licence, version
export function About() {
  const t = useT()
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: () => api.get('/health'), staleTime: Infinity })
  return (
    <dl className="divide-y divide-line rounded-2xl border border-line bg-bg2 px-5">
      <Row label={t('Version')}>
        SynCiné {health?.version || '—'}
        {health?.mode && ` · ${health.mode === 'personal' ? t('version personnelle') : t('version serveur')}`}
      </Row>
      <Row label={t('Contributeurs')}>
        <ul className="space-y-1">
          <li>
            <span className="font-medium text-text">Pierre Gauffre</span> — {t('créateur du projet et développement')}
          </li>
          <li>
            <span className="font-medium text-text">Claude</span> ({t('IA d’Anthropic')}) — {t('développement')}
          </li>
        </ul>
      </Row>
      <Row label={t('Licence')}>
        <p>{t('Logiciel libre, sous licence {license} : tu peux l’utiliser, l’étudier, le modifier et le partager.', { license: PROJECT.license })}</p>
        <p className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
          <a href={PROJECT.licenseUrl} target="_blank" rel="noreferrer" className={link}>
            <Scale className="h-3.5 w-3.5" /> {t('Texte de la licence')}
          </a>
          <a href={PROJECT.repo} target="_blank" rel="noreferrer" className={link}>
            <Github className="h-3.5 w-3.5" /> {t('Code source')}
          </a>
          <a href={PROJECT.securityUrl} target="_blank" rel="noreferrer" className={link}>
            <ShieldCheck className="h-3.5 w-3.5" /> {t('Signaler une faille')}
          </a>
        </p>
      </Row>
      <Row label={t('Données')}>
        <p className="flex items-start gap-2">
          <img
            src="https://www.themoviedb.org/assets/2/v4/logos/v2/blue_short-8e7b30f73a4020692ccca9c88bafe5dcb6f8a62a4c6bc55cd9ba82bb2cd95f6c.svg"
            alt="TMDB"
            className="mt-1 h-3 shrink-0"
          />
          <span>{t('Ce produit utilise l’API TMDB, mais n’est ni approuvé ni certifié par TMDB.')}</span>
        </p>
        <p className="mt-1.5">
          {t('Disponibilités streaming : JustWatch. Séances de cinéma : AlloCiné, Filmstarts, SensaCine, Beyazperde (Webedia). Suivi : Trakt, Letterboxd, Plex.')}
        </p>
        <p className="mt-1.5 text-text3">{t('SynCiné n’est affilié à aucun de ces services.')}</p>
      </Row>
      <Row label={t('Vie privée')}>
        {t('Tout reste sur ton serveur : SynCiné ne collecte rien et n’envoie tes données qu’aux services que tu as connectés.')}
      </Row>
    </dl>
  )
}
