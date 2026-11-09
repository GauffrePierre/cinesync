import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link2, LogIn, Unlink } from 'lucide-react'
import Button from '../ui/Button'
import { jellyfin } from '../../services/jellyfin'
import { toast } from '../../store/uiStore'
import { useT } from '../../i18n'

const input = 'h-10 w-full rounded-xl border border-line bg-bg px-3 text-sm outline-none placeholder:text-text3 focus:border-accent'

function Field({ label, hint, ...props }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-text2">{label}</span>
      <input {...props} className={input} />
      {hint && <span className="mt-1 block text-[11px] text-text3">{hint}</span>}
    </label>
  )
}

// Carte Jellyfin / Emby du Profil : serveur (admin) puis compte personnel (vus, connexion)
export default function JellyfinConnect({ status, isAdmin }) {
  const t = useT()
  const qc = useQueryClient()
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['status'] })
    qc.invalidateQueries({ queryKey: ['settings'] })
    qc.invalidateQueries({ queryKey: ['library'] })
  }
  const [server, setServer] = useState({ url: '', public_url: '', api_key: '' })
  const [account, setAccount] = useState({ username: '', password: '' })
  const onError = (e) => toast(e.message, 'error')
  const connect = useMutation({
    mutationFn: () => jellyfin.connectServer(server),
    onSuccess: (r) => {
      toast(t('Serveur {server} relié', { server: r.server }), 'success')
      setServer({ url: '', public_url: '', api_key: '' })
      refresh()
    },
    onError,
  })
  const disconnect = useMutation({ mutationFn: jellyfin.disconnectServer, onSuccess: refresh, onError })
  const link = useMutation({
    mutationFn: () => jellyfin.link(account.username, account.password),
    onSuccess: (r) => {
      toast(t('Compte {name} relié', { name: r.username }), 'success')
      setAccount({ username: '', password: '' })
      refresh()
    },
    onError,
  })
  const unlink = useMutation({ mutationFn: jellyfin.unlink, onSuccess: refresh, onError })
  const label = status?.kind === 'emby' ? 'Emby' : 'Jellyfin'

  return (
    <div className="space-y-4">
      {isAdmin && !status?.server_linked && (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            connect.mutate()
          }}
        >
          <Field
            label={t('Adresse du serveur')}
            placeholder="http://ip-du-serveur:8096"
            hint={t('Adresse vue depuis SynCiné (IP locale, pas localhost en Docker).')}
            value={server.url}
            onChange={(e) => setServer({ ...server, url: e.target.value })}
            required
          />
          <Field
            label={t('Adresse publique (facultatif)')}
            placeholder="https://jellyfin.exemple.fr"
            hint={t('Utilisée pour les liens « Lire » ouverts par la famille. Par défaut : l’adresse du serveur.')}
            value={server.public_url}
            onChange={(e) => setServer({ ...server, public_url: e.target.value })}
          />
          <Field
            label={t('Clé API')}
            type="password"
            placeholder={t('Tableau de bord → Clés API')}
            value={server.api_key}
            onChange={(e) => setServer({ ...server, api_key: e.target.value })}
            autoComplete="off"
            required
          />
          <Button type="submit" variant="primary" icon={Link2} loading={connect.isPending}>
            {t('Relier le serveur')}
          </Button>
        </form>
      )}

      {status?.server_linked && (
        <div className="space-y-3">
          <p className="text-sm text-text2">
            {t('Serveur {server}', { server: status.server || label })}
            {isAdmin && (
              <button onClick={() => disconnect.mutate()} className="ml-2 text-xs text-text3 hover:text-red-400">
                {t('Délier le serveur')}
              </button>
            )}
          </p>
          {status.linked ? (
            <div className="flex flex-wrap items-center gap-3 rounded-xl bg-bg3/60 p-3 text-sm">
              <span className="flex-1">{t('Ton compte {server} : {name}', { server: label, name: status.username })}</span>
              <Button size="sm" variant="ghost" icon={Unlink} onClick={() => unlink.mutate()} loading={unlink.isPending}>
                {t('Délier')}
              </Button>
            </div>
          ) : (
            <form
              className="space-y-3 rounded-xl bg-bg3/40 p-3"
              onSubmit={(e) => {
                e.preventDefault()
                link.mutate()
              }}
            >
              <p className="text-xs text-text2">
                {t('Relie ton compte {server} : ta bibliothèque, tes vus et ta progression dans SynCiné.', { server: label })}
              </p>
              <Field
                label={t('Identifiant {server}', { server: label })}
                value={account.username}
                onChange={(e) => setAccount({ ...account, username: e.target.value })}
                autoComplete="off"
                autoCapitalize="none"
                required
              />
              <Field
                label={t('Mot de passe')}
                type="password"
                value={account.password}
                onChange={(e) => setAccount({ ...account, password: e.target.value })}
                autoComplete="off"
              />
              <Button type="submit" icon={LogIn} loading={link.isPending}>
                {t('Relier mon compte')}
              </Button>
            </form>
          )}
        </div>
      )}
    </div>
  )
}
