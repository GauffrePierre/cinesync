import { useEffect, useRef, useState } from 'react'
import { Loader2, RefreshCw } from 'lucide-react'
import Button from './Button'
import { useT } from '../../i18n'

// Quick Connect (Jellyfin) : affiche le code à valider dans Jellyfin, puis interroge SynCiné toutes les 2 s.
// start() -> { id, code } ; check(id) -> { status: 'pending' } tant que le code n'est pas validé, sinon le résultat.
export default function QuickConnectCode({ start, check, onDone, onCancel }) {
  const t = useT()
  const [request, setRequest] = useState(null)
  const [error, setError] = useState(null)
  const [attempt, setAttempt] = useState(0)
  const done = useRef(false)

  useEffect(() => {
    let cancelled = false
    let timer
    setRequest(null)
    setError(null)
    start()
      .then((r) => {
        if (cancelled) return
        setRequest(r)
        const poll = async () => {
          try {
            const res = await check(r.id)
            if (cancelled || done.current) return
            if (res?.status === 'pending') timer = setTimeout(poll, 2000)
            else {
              done.current = true
              onDone(res)
            }
          } catch (err) {
            if (!cancelled) setError(err.status === 410 ? t('Code expiré : recommence') : err.message)
          }
        }
        timer = setTimeout(poll, 2000)
      })
      .catch((err) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt])

  return (
    <div className="space-y-3 rounded-xl border border-line bg-bg3/40 p-4 text-center">
      {error ? (
        <>
          <p className="text-sm text-red-400">{error}</p>
          <Button size="sm" variant="secondary" icon={RefreshCw} onClick={() => setAttempt((n) => n + 1)}>
            {t('Nouveau code')}
          </Button>
        </>
      ) : request ? (
        <>
          <p className="text-sm text-text2">{t('Dans Jellyfin (application ou site), ouvre ton profil → Quick Connect et saisis ce code :')}</p>
          <p className="font-mono text-3xl font-semibold tracking-[0.3em]" aria-live="polite">
            {request.code}
          </p>
          <p className="flex items-center justify-center gap-2 text-xs text-text3">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> {t('En attente de la validation dans Jellyfin…')}
          </p>
        </>
      ) : (
        <Loader2 className="mx-auto h-5 w-5 animate-spin text-text3" />
      )}
      {onCancel && (
        <button type="button" onClick={onCancel} className="text-xs text-text3 hover:text-text2">
          {t('Annuler')}
        </button>
      )}
    </div>
  )
}
