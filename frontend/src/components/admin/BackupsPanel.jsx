import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, DatabaseBackup, Download, Trash2 } from 'lucide-react'
import Button from '../ui/Button'
import Skeleton from '../ui/Skeleton'
import { admin } from '../../services/admin'
import { relativeTime } from '../../lib/format'
import { toast } from '../../store/uiStore'
import { fmtNumber, useT } from '../../i18n'

const KEEP = [3, 7, 14, 30]

const size = (bytes) => (bytes >= 1048576 ? `${fmtNumber(bytes / 1048576, { maximumFractionDigits: 1 })} Mo` : `${fmtNumber(Math.ceil(bytes / 1024))} Ko`)

// Sauvegardes de la base SQLite : une par jour (si activé), téléchargement, sauvegarde immédiate
export default function BackupsPanel() {
  const t = useT()
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['admin', 'backups'], queryFn: admin.backups })
  const done = (res) => qc.setQueryData(['admin', 'backups'], res)
  const onError = (e) => toast(e.message, 'error')
  const now = useMutation({ mutationFn: admin.backupNow, onSuccess: (r) => (done(r), toast(t('Sauvegarde créée'), 'success')), onError })
  const settings = useMutation({ mutationFn: admin.backupSettings, onSuccess: done, onError })
  const remove = useMutation({ mutationFn: admin.deleteBackup, onSuccess: done, onError })

  if (isLoading || !data) return <Skeleton className="h-40 w-full" />

  return (
    <div className="space-y-4">
      <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-line bg-bg2 px-3 py-3">
        <DatabaseBackup className="h-5 w-5 shrink-0 text-accent2" />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium">{t('Sauvegarde automatique chaque jour')}</span>
          <span className="block text-xs text-text2">{t('Comptes, réglages, connexions aux services et historique, dans le dossier data/backups du serveur.')}</span>
        </span>
        <input
          type="checkbox"
          checked={data.enabled}
          onChange={(e) => settings.mutate({ enabled: e.target.checked })}
          className="h-5 w-5 shrink-0 accent-[var(--accent)]"
        />
      </label>

      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-text2">
          {t('Sauvegardes à garder')}
          <select
            value={data.keep}
            onChange={(e) => settings.mutate({ keep: Number(e.target.value) })}
            className="h-9 rounded-lg border border-line bg-bg px-2 text-sm text-text outline-none focus:border-accent"
          >
            {[...new Set([...KEEP, data.keep])].sort((a, b) => a - b).map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <Button size="sm" icon={DatabaseBackup} onClick={() => now.mutate()} loading={now.isPending} className="ml-auto">
          {t('Sauvegarder maintenant')}
        </Button>
      </div>

      {data.last_error && (
        <p className="flex items-start gap-2 rounded-xl bg-red-500/10 p-3 text-xs text-red-400">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          {t('La dernière sauvegarde automatique a échoué : {error}', { error: data.last_error })}
        </p>
      )}

      {data.items.length === 0 ? (
        <p className="py-4 text-center text-sm text-text3">{t('Aucune sauvegarde pour le moment.')}</p>
      ) : (
        <ul className="divide-y divide-line rounded-xl border border-line">
          {data.items.map((b) => (
            <li key={b.name} className="flex items-center gap-3 px-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-xs">{b.name}</p>
                <p className="text-xs text-text3">
                  {relativeTime(b.created_at)} · {size(b.size)}
                </p>
              </div>
              <a href={admin.backupUrl(b.name)} download className="rounded-lg p-2 text-text2 hover:bg-bg3 hover:text-text" aria-label={t('Télécharger')} title={t('Télécharger')}>
                <Download className="h-4 w-4" />
              </a>
              <button
                onClick={() => window.confirm(t('Supprimer la sauvegarde {name} ?', { name: b.name })) && remove.mutate(b.name)}
                className="rounded-lg p-2 text-text2 hover:bg-bg3 hover:text-red-400"
                aria-label={t('Supprimer')}
                title={t('Supprimer')}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <p className="text-xs text-text3">
        {t('Une sauvegarde contient les jetons des services et les mots de passe chiffrés : garde les copies téléchargées en lieu sûr. Pour restaurer, suis le guide de restauration (wiki, « Comptes et sécurité »).')}
      </p>
    </div>
  )
}
