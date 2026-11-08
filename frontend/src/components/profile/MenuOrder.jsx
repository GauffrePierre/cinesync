import { useEffect, useState } from 'react'
import { GripVertical, RotateCcw } from 'lucide-react'
import Button from '../ui/Button'
import { useSidebarItems } from '../layout/nav'
import { useUpdateSettings } from '../../hooks/useMedia'
import { useT } from '../../i18n'

// Ordre des onglets du menu de la version ordinateur (enregistré pour ce compte).
// Glisser-déposer à la souris ; au clavier : Alt + flèche haut / bas sur un onglet.
export default function MenuOrder({ settings }) {
  const t = useT()
  const update = useUpdateSettings()
  const items = useSidebarItems()
  const [order, setOrder] = useState(() => items.map((i) => i.key))
  const [dragging, setDragging] = useState(null)
  const byKey = Object.fromEntries(items.map((i) => [i.key, i]))

  // Réglage modifié ailleurs (ou onglets visibles qui changent) : on repart de l'ordre enregistré
  const saved = items.map((i) => i.key).join(',')
  useEffect(() => {
    if (!dragging) setOrder(saved.split(','))
  }, [saved]) // eslint-disable-line react-hooks/exhaustive-deps

  const save = (next) => {
    if (next.join(',') !== saved) update.mutate({ nav_order: next })
  }
  const moveTo = (key, target) => {
    setOrder((current) => {
      const from = current.indexOf(key)
      const to = current.indexOf(target)
      if (from < 0 || to < 0 || from === to) return current
      const next = [...current]
      next.splice(from, 1)
      next.splice(to, 0, key)
      return next
    })
  }

  return (
    <div>
      <ol className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-bg2">
        {order.filter((k) => byKey[k]).map((key, i) => {
          const item = byKey[key]
          return (
            <li
              key={key}
              draggable
              tabIndex={0}
              aria-label={t(item.label)}
              onDragStart={(e) => {
                setDragging(key)
                e.dataTransfer.effectAllowed = 'move'
                e.dataTransfer.setData('text/plain', key)
              }}
              onDragOver={(e) => {
                e.preventDefault()
                if (dragging && dragging !== key) moveTo(dragging, key)
              }}
              onDrop={(e) => e.preventDefault()}
              onDragEnd={() => {
                setDragging(null)
                save(order)
              }}
              onKeyDown={(e) => {
                if (!e.altKey || !['ArrowUp', 'ArrowDown'].includes(e.key)) return
                e.preventDefault()
                const next = [...order]
                const j = i + (e.key === 'ArrowUp' ? -1 : 1)
                if (j < 0 || j >= next.length) return
                ;[next[i], next[j]] = [next[j], next[i]]
                setOrder(next)
                save(next)
              }}
              className={`flex cursor-grab select-none items-center gap-3 px-3 py-2.5 outline-none transition active:cursor-grabbing focus-visible:bg-bg3 ${
                dragging === key ? 'bg-accent/10 opacity-60' : 'hover:bg-bg3/60'
              }`}
            >
              <GripVertical className="h-4 w-4 shrink-0 text-text3" />
              <span className="w-5 text-right text-xs tabular-nums text-text3">{i + 1}</span>
              <item.icon className="h-4 w-4 shrink-0 text-text2" />
              <span className="flex-1 text-sm">{t(item.label)}</span>
            </li>
          )
        })}
      </ol>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <p className="text-xs text-text3">{t('Fais glisser un onglet pour le déplacer.')}</p>
        {(settings?.nav_order || []).length > 0 && (
          <Button size="sm" variant="ghost" icon={RotateCcw} onClick={() => update.mutate({ nav_order: [] })}>
            {t('Ordre par défaut')}
          </Button>
        )}
      </div>
    </div>
  )
}
