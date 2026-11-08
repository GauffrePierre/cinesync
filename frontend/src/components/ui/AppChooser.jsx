import { useEffect, useState } from 'react'
import { ExternalLink, Loader2, Smartphone } from 'lucide-react'
import Modal from './Modal'
import { api } from '../../services/api'
import { setAppPref } from '../../lib/appLinks'
import { useT } from '../../i18n'

// iPhone / iPad : ouvrir le titre dans l'application (Plex, Netflix) ou dans le navigateur.
// Plex : le lien de l'app est la page watch.plex.tv du titre, demandée au serveur si besoin.
export default function AppChooser() {
  const t = useT()
  const [target, setTarget] = useState(null)
  const [appHref, setAppHref] = useState(null)
  const [loading, setLoading] = useState(false)
  const [remember, setRemember] = useState(false)

  useEffect(() => {
    const onOpen = async (e) => {
      const d = e.detail
      setRemember(false)
      setTarget(d)
      setAppHref(d.scheme)
      const ref = d.ref
      if (!d.scheme && d.app === 'Plex' && ref?.id) {
        setLoading(true)
        try {
          const q = new URLSearchParams()
          if (ref.season != null) q.set('season', ref.season)
          if (ref.episode != null) q.set('episode', ref.episode)
          const r = await api.get(`/plex/watch-link/${ref.mediaType}/${ref.id}${q.size ? `?${q}` : ''}`)
          setAppHref(r.url)
        } catch {
          setAppHref(null)
        } finally {
          setLoading(false)
        }
      }
    }
    window.addEventListener('cinesync:open-app', onOpen)
    return () => window.removeEventListener('cinesync:open-app', onOpen)
  }, [])

  const close = () => setTarget(null)
  const btn = 'flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-medium transition active:scale-[0.98]'

  return (
    <Modal open={!!target} onClose={close} title={target ? t('Ouvrir dans {app}', { app: target.app }) : ''}>
      {target && (
        <div className="space-y-2">
          {/* Vrais liens touchés par l'utilisateur : c'est ce qu'iOS accepte pour ouvrir une autre app */}
          {loading ? (
            <span className={`${btn} bg-accent/60 text-white`}>
              <Loader2 className="h-4 w-4 animate-spin" /> {t("Ouvrir l'app {app}", { app: target.app })}
            </span>
          ) : appHref ? (
            <a
              href={appHref}
              onClick={() => {
                if (remember) setAppPref(target.app, 'app')
                setTimeout(close, 300)
              }}
              className={`${btn} bg-accent text-white`}
            >
              <Smartphone className="h-4 w-4" /> {t("Ouvrir l'app {app}", { app: target.app })}
            </a>
          ) : (
            <p className="rounded-xl bg-bg3/60 px-3 py-2 text-xs text-text2">{t("Ce titre n'a pas été trouvé dans le catalogue de l'app : ouvre-le dans le navigateur.")}</p>
          )}
          <a href={target.url} target="_blank" rel="noreferrer" onClick={close} className={`${btn} border border-line bg-bg3 text-text`}>
            <ExternalLink className="h-4 w-4" /> {t('Ouvrir dans le navigateur')}
          </a>
          {target.app === 'Plex' && appHref && <p className="text-[11px] text-text3">{t("Dans l'app Plex, choisis ensuite ton serveur pour lancer la lecture.")}</p>}
          {appHref && (
            <label className="flex items-center gap-2 pt-2 text-xs text-text2">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="h-4 w-4" />
              {t("Toujours ouvrir l'app {app} sans demander", { app: target.app })}
            </label>
          )}
        </div>
      )}
    </Modal>
  )
}
