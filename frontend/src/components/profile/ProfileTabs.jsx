import { useT } from '../../i18n'

// Onglets du Profil : toujours sur une ligne ; sur téléphone, pictogramme au-dessus du libellé (colonnes égales)
export default function ProfileTabs({ value, onChange, options, className = '' }) {
  const t = useT()
  return (
    <div role="tablist" className={`grid w-full auto-cols-fr grid-flow-col gap-1 rounded-xl border border-line bg-bg2 p-1 sm:inline-grid sm:w-fit sm:auto-cols-auto ${className}`}>
      {options.map(({ value: v, label, icon: Icon }) => {
        const active = v === value
        return (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(v)}
            className={`flex min-w-0 flex-col items-center gap-0.5 rounded-lg px-1.5 py-1.5 text-[11px] font-medium transition sm:flex-row sm:gap-1.5 sm:px-4 sm:text-sm ${
              active ? 'bg-bg3 text-text shadow-sm' : 'text-text2 hover:text-text'
            }`}
          >
            <Icon className="h-4 w-4 shrink-0" />
            <span className="max-w-full truncate">{t(label)}</span>
          </button>
        )
      })}
    </div>
  )
}
