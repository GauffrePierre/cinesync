import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import Poster from '../media/Poster'
import PlatformBadge from '../ui/PlatformBadge'
import { detailPath, formatDate, formatMonth, mediaLabel } from '../../lib/format'
import { useT } from '../../i18n'

const WEEKDAYS = ['lun', 'mar', 'mer', 'jeu', 'ven', 'sam', 'dim']
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

export default function CalendarView({ items = [] }) {
  const [cursor, setCursor] = useState(() => {
    const d = new Date()
    return new Date(d.getFullYear(), d.getMonth(), 1)
  })
  const [selected, setSelected] = useState(() => iso(new Date()))
  const t = useT()

  const byDate = useMemo(() => {
    const m = {}
    items.forEach((i) => i.release_date && (m[i.release_date] ||= []).push(i))
    return m
  }, [items])

  // Grille du mois, semaines commençant le lundi
  const days = useMemo(() => {
    const first = new Date(cursor)
    const offset = (first.getDay() + 6) % 7
    const start = new Date(first)
    start.setDate(1 - offset)
    return Array.from({ length: 42 }, (_, n) => {
      const d = new Date(start)
      d.setDate(start.getDate() + n)
      return d
    })
  }, [cursor])

  const today = iso(new Date())
  const move = (n) => setCursor((c) => new Date(c.getFullYear(), c.getMonth() + n, 1))
  const selectedItems = byDate[selected] || []

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="rounded-3xl border border-line bg-bg2 p-3 md:p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{formatMonth(cursor)}</h2>
          <div className="flex gap-1">
            <button onClick={() => move(-1)} className="rounded-full p-2 text-text2 hover:bg-bg3 hover:text-text" aria-label={t('Mois précédent')}>
              <ChevronLeft className="h-5 w-5" />
            </button>
            <button onClick={() => move(1)} className="rounded-full p-2 text-text2 hover:bg-bg3 hover:text-text" aria-label={t('Mois suivant')}>
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>
        </div>
        <div className="grid grid-cols-7 gap-1 text-center text-[11px] font-medium text-text3">
          {WEEKDAYS.map((d) => (
            <div key={d} className="pb-2">
              {t(d)}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-1">
          {days.map((d) => {
            const key = iso(d)
            const list = byDate[key] || []
            const inMonth = d.getMonth() === cursor.getMonth()
            const isSel = key === selected
            return (
              <button
                key={key}
                onClick={() => setSelected(key)}
                className={`relative flex aspect-square flex-col overflow-hidden rounded-xl p-1 text-left transition md:aspect-[4/5] ${
                  isSel ? 'bg-accent/15 ring-1 ring-accent' : 'hover:bg-bg3'
                } ${inMonth ? '' : 'opacity-35'}`}
              >
                <span
                  className={`z-10 inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-medium ${
                    key === today ? 'bg-accent text-white' : ''
                  }`}
                >
                  {d.getDate()}
                </span>
                {list.length > 0 && (
                  <>
                    <div className="absolute inset-x-1 bottom-1 top-6 hidden gap-0.5 md:flex">
                      {list.slice(0, 2).map((i) => (
                        <div key={i.id} className="min-w-0 flex-1 overflow-hidden rounded-md">
                          <Poster src={i.poster} title={i.title} mediaType={i.media_type} rounded="rounded-md" className="h-full" />
                        </div>
                      ))}
                    </div>
                    <span className="absolute bottom-1 right-1 rounded-md bg-accent px-1 text-[9px] font-semibold text-white">{list.length}</span>
                  </>
                )}
              </button>
            )
          })}
        </div>
      </div>

      <div>
        <h3 className="mb-3 font-semibold">{formatDate(selected)}</h3>
        {selectedItems.length === 0 ? (
          <p className="text-sm text-text3">{t('Aucune sortie ce jour-là.')}</p>
        ) : (
          <div className="space-y-2">
            {selectedItems.map((i) => (
              <Link key={`${i.media_type}-${i.id}`} to={detailPath(i)} className="flex gap-3 rounded-2xl p-2 hover:bg-bg2">
                <div className="w-12 shrink-0">
                  <Poster src={i.poster} title={i.title} mediaType={i.media_type} rounded="rounded-lg" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{i.title}</p>
                  <p className="text-xs text-text2">{mediaLabel(i.media_type)}</p>
                  <div className="mt-1 flex -space-x-1">
                    {i.providers?.slice(0, 4).map((p) => (
                      <PlatformBadge key={p.id} provider={p} size="xs" ring={false} />
                    ))}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
