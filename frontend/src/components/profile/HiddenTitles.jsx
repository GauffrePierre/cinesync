import { useState } from 'react'
import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, EyeOff, Film, RotateCcw, Search, Tv } from 'lucide-react'
import Button from '../ui/Button'
import { library } from '../../services/library'
import { useUndislike } from '../../hooks/useMedia'
import { useT } from '../../i18n'

// Titres marqués « pas intéressé » : une ligne repliée ; dépliée, une liste (défilante) pour en rétablir
export default function HiddenTitles() {
  const t = useT()
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const { data } = useQuery({ queryKey: ['disliked'], queryFn: library.disliked })
  const undo = useUndislike()
  const list = data?.results || []
  const shown = q ? list.filter((i) => (i.title || '').toLowerCase().includes(q.toLowerCase())) : list

  if (!list.length) {
    return (
      <p className="flex items-center gap-2 rounded-2xl border border-line bg-bg2 px-4 py-3 text-sm text-text3">
        <EyeOff className="h-4 w-4 shrink-0" /> {t('Aucun titre masqué. La croix sur une affiche retire un titre de tes suggestions.')}
      </p>
    )
  }
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-bg2">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-bg3">
        <EyeOff className="h-4 w-4 shrink-0 text-text3" />
        <span className="flex-1 text-sm">{list.length > 1 ? t('{n} titres masqués', { n: list.length }) : t('{n} titre masqué', { n: list.length })}</span>
        <ChevronDown className={`h-4 w-4 text-text3 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="border-t border-line p-3">
          {list.length > 8 && (
            <div className="relative mb-2">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text3" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={t('Chercher un titre…')}
                aria-label={t('Chercher un titre…')}
                className="h-9 w-full rounded-xl border border-line bg-bg pl-9 pr-3 text-sm outline-none focus:border-accent"
              />
            </div>
          )}
          <ul className="max-h-80 space-y-1.5 overflow-y-auto pr-1">
            {shown.map((item) => (
              <li key={`${item.media_type}-${item.id}`} className="flex items-center gap-3 rounded-xl bg-bg p-2">
                <Link to={`/${item.media_type}/${item.id}`} className="flex h-12 w-8 shrink-0 items-center justify-center overflow-hidden rounded-md bg-bg3">
                  {item.poster ? (
                    <img src={item.poster} alt="" loading="lazy" className="h-full w-full object-cover" />
                  ) : item.media_type === 'tv' ? (
                    <Tv className="h-4 w-4 text-text3" />
                  ) : (
                    <Film className="h-4 w-4 text-text3" />
                  )}
                </Link>
                <span className="min-w-0 flex-1 truncate text-sm">{item.title || `#${item.id}`}</span>
                <Button size="sm" variant="ghost" icon={RotateCcw} onClick={() => undo.mutate({ mediaType: item.media_type, id: item.id })}>
                  {t('Rétablir')}
                </Button>
              </li>
            ))}
            {!shown.length && <li className="p-2 text-sm text-text3">{t('Aucun titre ne correspond.')}</li>}
          </ul>
        </div>
      )}
    </div>
  )
}
