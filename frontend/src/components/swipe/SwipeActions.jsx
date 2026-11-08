import { Check, Eye, Star, X } from 'lucide-react'
import { useT } from '../../i18n'

const ACTIONS = [
  { action: 'skip', label: 'Passer', icon: X, cls: 'h-14 w-14 text-red-400 hover:bg-red-500/15', iconCls: 'h-7 w-7' },
  { action: 'seen', label: 'Déjà vu', icon: Eye, cls: 'h-12 w-12 text-sky-400 hover:bg-sky-500/15', iconCls: 'h-5 w-5' },
  { action: 'watchlist', label: 'Watchlist', icon: Star, cls: 'h-12 w-12 text-amber-400 hover:bg-amber-500/15', iconCls: 'h-5 w-5' },
  { action: 'like', label: "J'aime", icon: Check, cls: 'h-14 w-14 text-emerald-400 hover:bg-emerald-500/15', iconCls: 'h-7 w-7' },
]

export default function SwipeActions({ onAction, disabled }) {
  const t = useT()
  return (
    <div className="flex items-center justify-center gap-4 md:gap-5">
      {ACTIONS.map(({ action, label, icon: Icon, cls, iconCls }) => (
        <div key={action} className="flex flex-col items-center gap-1.5">
          <button
            onClick={() => onAction(action)}
            disabled={disabled}
            className={`flex items-center justify-center rounded-full border border-white/10 bg-white/5 backdrop-blur-xl transition active:scale-90 disabled:opacity-40 ${cls}`}
            aria-label={t(label)}
          >
            <Icon className={iconCls} strokeWidth={2.4} />
          </button>
          <span className="text-[11px] font-medium text-white/60">{t(label)}</span>
        </div>
      ))}
    </div>
  )
}
