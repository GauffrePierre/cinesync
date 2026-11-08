import { Fragment, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowRightLeft, CheckCircle2, RefreshCw, XCircle } from 'lucide-react'
import Button from '../ui/Button'
import Modal from '../ui/Modal'
import { useSettings, useSyncStatus, useUpdateSettings } from '../../hooks/useMedia'
import { library, SOURCE_LABELS } from '../../services/library'
import { relativeTime } from '../../lib/format'
import { toast } from '../../store/uiStore'
import { t as tNow, useT } from '../../i18n'

// Phrase traduite dont les {variables} sont remplacées par des éléments React
const rich = (str, nodes) =>
  str.split(/(\{\w+\})/).map((part, i) => {
    const k = part.match(/^\{(\w+)\}$/)?.[1]
    return k && k in nodes ? <Fragment key={i}>{nodes[k]}</Fragment> : part
  })

function PlanLine({ label, n, examples }) {
  const t = useT()
  if (!n) return null
  return (
    <li>
      {rich(t('{label} : {n}'), { label: t(label), n: <span className="font-medium">{n}</span> })}
      {examples?.length > 0 && <span className="block truncate text-[11px] text-text3">{t('ex. {list}', { list: examples.join(', ') })}</span>}
    </li>
  )
}

function pushedSummary(p) {
  if (!p) return null
  const parts = []
  const lines = [
    ['added', '{n} ajouté(s) à la watchlist sur {service}'],
    ['removed', '{n} retiré(s) de la watchlist sur {service}'],
    ['watched', '{n} vu(s) ajoutés sur {service}'],
    ['ratings', '{n} note(s) ajoutées sur {service}'],
  ]
  for (const [k, key] of lines) {
    for (const [svc, n] of Object.entries(p[k] || {})) if (n) parts.push(tNow(key, { n, service: SOURCE_LABELS[svc] || svc }))
  }
  return parts.length ? parts.join(' · ') : tNow('Tout était déjà identique')
}

// Synchronisation : collecte de l'existant + synchronisation bidirectionnelle automatique
export default function SyncPanel() {
  const t = useT()
  const qc = useQueryClient()
  const { data: status } = useSyncStatus()
  const { data: settings } = useSettings()
  const update = useUpdateSettings()
  const [confirm, setConfirm] = useState(false)
  const preview = useQuery({ queryKey: ['sync-preview'], queryFn: library.syncPreview, enabled: confirm, staleTime: 0 })

  const refreshAll = () => {
    for (const k of ['sync-status', 'watchlist', 'library-keys', 'media', 'sync-preview']) qc.invalidateQueries({ queryKey: [k] })
  }

  const pull = useMutation({
    mutationFn: library.syncNow,
    onSuccess: (r) => {
      toast(r.pushed ? t('Synchronisé — {summary}', { summary: pushedSummary(r.pushed) }) : t('Données récupérées'), 'success')
      refreshAll()
    },
    onError: (e) => toast(e.message, 'error'),
  })

  const enable = async () => {
    await update.mutateAsync({ auto_sync: true })
    setConfirm(false)
    pull.mutate()
  }

  const last = status?.last_pull
  const auto = settings?.auto_sync
  const plan = preview.data

  return (
    <div className="rounded-2xl border border-line bg-bg2 p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-text2">
          {last?.at ? (
            rich(t('Dernière synchronisation {when} · {n} titres suivis'), {
              when: relativeTime(last.at),
              n: <span className="text-text">{last.titles}</span>,
            })
          ) : (
            t('Pas encore synchronisé')
          )}
        </p>
        <Button size="sm" icon={RefreshCw} loading={pull.isPending} onClick={() => pull.mutate()}>
          {t('Synchroniser maintenant')}
        </Button>
      </div>

      {last?.sources && (
        <div className="mb-4 grid gap-2 sm:grid-cols-3">
          {Object.entries(last.sources).map(([src, s]) => (
            <div key={src} className="rounded-xl bg-bg3 px-3 py-2.5">
              <p className="flex items-center gap-1.5 text-sm font-medium">
                {s.ok ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : <XCircle className="h-4 w-4 text-red-400" />}
                {SOURCE_LABELS[src] || src}
              </p>
              <p className="mt-0.5 text-[11px] text-text3">
                {s.ok
                  ? [s.watchlist != null && t('{n} en watchlist', { n: s.watchlist }), s.watched != null && t('{n} vus', { n: s.watched }), s.ratings && t('{n} notes', { n: s.ratings })].filter(Boolean).join(' · ')
                  : s.error}
              </p>
            </div>
          ))}
        </div>
      )}

      <div className="rounded-xl border border-dashed border-line p-3">
        <div className="flex flex-wrap items-center gap-3">
          <ArrowRightLeft className="h-4 w-4 shrink-0 text-accent2" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">{t('Synchronisation automatique Trakt ⇄ Plex')}</p>
            <p className="text-xs text-text2">
              {t('Toutes les 30 min : watchlists identiques des deux côtés (ajouts et retraits), titres vus et notes recopiés là où ils manquent.')}
            </p>
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={!!auto}
              onChange={(e) => (e.target.checked ? setConfirm(true) : update.mutate({ auto_sync: false }))}
              className="h-5 w-5 accent-[var(--accent)]"
            />
            {auto ? t('Activée') : t('Désactivée')}
          </label>
        </div>
        {auto && last?.pushed && <p className="mt-2 text-xs text-text3">{t('Dernier passage : {summary}', { summary: pushedSummary(last.pushed) })}</p>}
        {last?.pushed?.warnings?.map((w) => (
          <p key={w} className="mt-2 flex gap-2 text-xs text-amber-500">
            <AlertTriangle className="h-4 w-4 shrink-0" /> {w}
          </p>
        ))}
      </div>

      <Modal open={confirm} onClose={() => setConfirm(false)} title={t('Activer la synchronisation')}>
        {preview.isLoading ? (
          <p className="text-sm text-text2">{t('Calcul de ce qui va être synchronisé…')}</p>
        ) : plan ? (
          <div className="space-y-3 text-sm">
            <p className="text-text2">{t("Première synchronisation, d'après tes données actuelles :")}</p>
            {['trakt', 'plex'].map(
              (svc) =>
                plan[svc] && (
                  <div key={svc} className="rounded-xl bg-bg3 px-3 py-2.5">
                    <p className="mb-1 font-medium">{t('Vers {service}', { service: SOURCE_LABELS[svc] })}</p>
                    <ul className="space-y-1 text-xs text-text2">
                      <PlanLine label="Ajouts à la watchlist" n={plan[svc].watchlist_add} examples={plan[svc].watchlist_add_examples} />
                      <PlanLine label="Retraits de la watchlist" n={plan[svc].watchlist_remove} examples={plan[svc].watchlist_remove_examples} />
                      <PlanLine label="Titres vus ajoutés" n={plan[svc].watched_add} />
                      <PlanLine label="Notes ajoutées" n={plan[svc].ratings_add} />
                      {!plan[svc].watchlist_add && !plan[svc].watchlist_remove && !plan[svc].watched_add && !plan[svc].ratings_add && <li>{t('Rien à changer')}</li>}
                    </ul>
                  </div>
                ),
            )}
            {plan.warnings?.map((w) => (
              <p key={w} className="flex gap-2 text-xs text-amber-500">
                <AlertTriangle className="h-4 w-4 shrink-0" /> {w}
              </p>
            ))}
            <p className="text-xs text-text3">{t("Ensuite, un titre ajouté ou retiré d'un côté le sera aussi de l'autre.")}</p>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="ghost" size="sm" onClick={() => setConfirm(false)}>
                {t('Annuler')}
              </Button>
              <Button variant="primary" size="sm" loading={update.isPending || pull.isPending} onClick={enable}>
                {t('Activer et synchroniser')}
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-red-400">{preview.error?.message}</p>
        )}
      </Modal>
    </div>
  )
}
