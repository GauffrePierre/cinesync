import { EyeOff, Sparkles } from 'lucide-react'
import { useUpdateSettings } from '../../hooks/useMedia'
import { useT } from '../../i18n'

// Réglages de ce que SynCiné propose (Découvrir, recommandations des fiches). D'autres viendront s'ajouter ici.
const OPTIONS = [
  {
    key: 'hide_seen',
    icon: EyeOff,
    label: 'Ne plus proposer les titres déjà vus',
    hint: 'Films vus, et séries vues sans nouvel épisode depuis ton dernier visionnage. Une série qui a de nouveaux épisodes reste proposée.',
    fallback: false,
  },
]

const RECENT = [0, 7, 14, 30, 60, 90]

export default function DiscoverySettings({ settings }) {
  const t = useT()
  const update = useUpdateSettings()
  return (
    <div className="space-y-2">
      {OPTIONS.map(({ key, icon: Icon, label, hint, fallback }) => (
        <label key={key} className="flex cursor-pointer items-center gap-3 rounded-xl border border-line bg-bg2 px-3 py-3">
          <Icon className="h-5 w-5 shrink-0 text-accent2" />
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-medium">{t(label)}</span>
            <span className="block text-xs text-text2">{t(hint)}</span>
          </span>
          <input
            type="checkbox"
            checked={settings?.[key] ?? fallback}
            onChange={(e) => update.mutate({ [key]: e.target.checked })}
            className="h-5 w-5 shrink-0 accent-[var(--accent)]"
          />
        </label>
      ))}
      <label className="flex items-center gap-3 rounded-xl border border-line bg-bg2 px-3 py-3">
        <Sparkles className="h-5 w-5 shrink-0 text-accent2" />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium">{t('Mettre en avant les sorties de ma watchlist')}</span>
          <span className="block text-xs text-text2">
            {t('Films sortis au cinéma ou en streaming, nouvelles saisons et nouveaux épisodes : en tête de Découvrir pendant la période choisie.')}
          </span>
        </span>
        <select
          value={settings?.recent_days ?? 30}
          onChange={(e) => update.mutate({ recent_days: Number(e.target.value) })}
          aria-label={t('Période')}
          className="h-9 shrink-0 rounded-lg border border-line bg-bg px-2 text-sm text-text outline-none focus:border-accent"
        >
          {RECENT.map((n) => (
            <option key={n} value={n}>
              {n ? t('{n} jours', { n }) : t('Désactivé')}
            </option>
          ))}
        </select>
      </label>
    </div>
  )
}
