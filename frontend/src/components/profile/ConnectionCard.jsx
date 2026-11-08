import { useEffect, useState } from 'react'
import { CheckCircle2, ExternalLink, Eye, EyeOff, XCircle } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import Button from '../ui/Button'
import { user } from '../../services/user'
import { useUpdateSettings } from '../../hooks/useMedia'
import { toast } from '../../store/uiStore'
import { useT } from '../../i18n'

function Field({ field, value, onChange, savedPreview }) {
  const t = useT()
  const [show, setShow] = useState(false)
  const isSecret = field.secret
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-text2">{t(field.label)}</span>
      <div className="relative">
        <input
          type={isSecret && !show ? 'password' : 'text'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={isSecret && savedPreview ? t('Enregistré ({preview}) — laisser vide pour conserver', { preview: savedPreview }) : t(field.placeholder)}
          autoComplete="off"
          spellCheck={false}
          className="h-11 w-full rounded-xl border border-line bg-bg px-3 pr-10 text-sm outline-none transition placeholder:text-text3 focus:border-accent"
        />
        {isSecret && (
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-text3 hover:text-text"
            aria-label={show ? t('Masquer') : t('Afficher')}
          >
            {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        )}
      </div>
      {field.hint && <span className="mt-1 block text-xs text-text3">{t(field.hint)}</span>}
    </label>
  )
}

/**
 * Carte de connexion d'un service : champs, enregistrement, test.
 * fields : [{ name, label, placeholder, secret, hint }]
 */
export default function ConnectionCard({ service, title, color, description, helpUrl, helpLabel, fields = [], settings, connected, optional, children, testable = true, manualLabel }) {
  const t = useT()
  const qc = useQueryClient()
  const update = useUpdateSettings()
  const [values, setValues] = useState({})
  const [result, setResult] = useState(null)
  // manualLabel : les champs sont repliés sous la connexion principale (ex. Plex : compte d'abord, saisie manuelle en option)
  const [manualOpen, setManualOpen] = useState(false)
  const collapsible = !!manualLabel
  const showFields = fields.length > 0 && (!collapsible || manualOpen)

  // Valeurs initiales : champs non secrets depuis les réglages, secrets vides
  useEffect(() => {
    if (!settings) return
    setValues(Object.fromEntries(fields.map((f) => [f.name, f.secret ? '' : settings[f.name] ?? ''])))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings])

  const test = useMutation({
    mutationFn: () => user.test(service),
    onSuccess: (r) => {
      setResult(r)
      qc.invalidateQueries({ queryKey: ['status'] })
    },
    onError: (e) => setResult({ ok: false, message: e.message }),
  })

  const dirty = fields.some((f) => (f.secret ? values[f.name] : (values[f.name] ?? '') !== (settings?.[f.name] ?? '')))

  const save = async () => {
    const patch = {}
    fields.forEach((f) => {
      const v = (values[f.name] ?? '').trim()
      if (f.secret ? v : v !== (settings?.[f.name] ?? '')) patch[f.name] = v
    })
    await update.mutateAsync(patch)
    setValues((vals) => Object.fromEntries(Object.entries(vals).map(([k, v]) => [k, fields.find((f) => f.name === k)?.secret ? '' : v])))
    toast(t('{name} enregistré', { name: t(title) }), 'success')
    if (testable) test.mutate()
  }

  const clear = async () => {
    await update.mutateAsync(Object.fromEntries(fields.map((f) => [f.name, ''])))
    setResult(null)
    toast(t('{name} déconnecté', { name: t(title) }), 'info')
  }

  return (
    <div className="min-w-0 rounded-2xl border border-line bg-bg2 p-4 sm:p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-sm font-semibold text-white" style={{ background: color }}>
            {title[0]}
          </span>
          <div>
            <p className="font-medium">
              {t(title)} {optional && <span className="text-xs font-normal text-text3">· {t('optionnel')}</span>}
            </p>
            <p className="text-xs text-text2">{t(description)}</p>
          </div>
        </div>
        <span
          className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium ${
            connected ? 'bg-emerald-500/15 text-emerald-500' : 'bg-bg3 text-text3'
          }`}
        >
          {connected ? t('Connecté') : t('Non configuré')}
        </span>
      </div>

      {collapsible && children}

      {collapsible && fields.length > 0 && (
        <button onClick={() => setManualOpen((o) => !o)} className="mt-3 text-xs text-text2 hover:text-text">
          {manualOpen ? '▾' : '▸'} {t(manualLabel)}
        </button>
      )}

      {showFields && (
        <div className={`grid grid-cols-1 gap-3 ${collapsible ? 'mt-3' : ''}`}>
          {fields.map((f) => (
            <Field
              key={f.name}
              field={f}
              value={values[f.name] ?? ''}
              onChange={(v) => setValues((s) => ({ ...s, [f.name]: v }))}
              savedPreview={settings?.secrets?.[f.name]}
            />
          ))}
        </div>
      )}

      {!collapsible && children}

      {result && (
        <div className={`mt-4 flex items-start gap-2 rounded-xl px-3 py-2.5 text-sm ${result.ok ? 'bg-emerald-500/10 text-emerald-500' : 'bg-red-500/10 text-red-400'}`}>
          {result.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0" />}
          {result.message}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {showFields && (
          <Button variant="primary" size="sm" onClick={save} loading={update.isPending} disabled={!dirty}>
            {t('Enregistrer')}
          </Button>
        )}
        {testable && connected && (
          <Button size="sm" onClick={() => test.mutate()} loading={test.isPending}>
            {t('Tester la connexion')}
          </Button>
        )}
        {connected && showFields && (
          <Button variant="ghost" size="sm" onClick={clear}>
            {t('Effacer')}
          </Button>
        )}
        {helpUrl && (
          <a href={helpUrl} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-xs text-text2 hover:text-accent2">
            {helpLabel ? t(helpLabel) : t('Aide')} <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>
    </div>
  )
}
