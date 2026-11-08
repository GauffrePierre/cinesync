import { useState } from 'react'
import { fmtNumber, useT } from '../../i18n'

/*
 * Graphiques des statistiques — HTML/CSS, sans bibliothèque.
 * Règles (guide dataviz) : barres <= 24px, extrémité arrondie 4px et base carrée, écart de 2px
 * couleur de surface entre segments, grille en filet plein discret, une seule échelle,
 * texte toujours en couleur de texte (jamais celle de la série), infobulle au survol ET au focus,
 * vue tableau équivalente. Couleurs : --series-1 / --series-2 (palette validée, clair et sombre).
 */

const fmt = (n) => (n >= 10000 ? `${Math.round(n / 1000)} k` : fmtNumber(Math.round(n)))

function niceMax(v) {
  if (v <= 0) return 1
  const p = 10 ** Math.floor(Math.log10(v))
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((m) => m >= v)
}

export function Legend({ items }) {
  return (
    <div className="flex flex-wrap items-center gap-4 text-xs text-text2">
      {items.map((it) => (
        <span key={it.label} className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: it.color }} />
          {it.label}
        </span>
      ))}
    </div>
  )
}

/**
 * Colonnes (empilées si plusieurs séries).
 * data : [{ label, sub?, values: { [serie]: n } }] ; series : [{ key, label, color }]
 */
export function ColumnChart({ data, series, height = 200, onSelect, selected, formatValue = fmt, labelEvery = 1, ariaLabel }) {
  const [hover, setHover] = useState(null)
  const t = useT()
  const totals = data.map((d) => series.reduce((a, s) => a + (d.values[s.key] || 0), 0))
  const max = niceMax(Math.max(0, ...totals))
  const ticks = [0, max / 2, max]
  const active = hover ?? selected

  return (
    <div className="relative pt-3" role="group" aria-label={ariaLabel}>
      <div className="flex">
        {/* Graduations */}
        <div className="relative mr-2 w-10 shrink-0 text-right text-[10px] tabular-nums text-text3" style={{ height }}>
          {ticks.map((t) => (
            <span key={t} className="absolute right-0 -translate-y-1/2" style={{ bottom: `${(t / max) * 100}%` }}>
              {formatValue(t)}
            </span>
          ))}
        </div>
        <div className="relative min-w-0 flex-1" style={{ height }}>
          {ticks.map((t) => (
            <div key={t} className="absolute inset-x-0 h-px bg-[var(--viz-grid)]" style={{ bottom: `${(t / max) * 100}%` }} />
          ))}
          <div className="absolute inset-0 flex items-end">
            {data.map((d, i) => {
              const total = totals[i]
              const visible = series.filter((s) => d.values[s.key] > 0)
              return (
                <button
                  key={d.label + i}
                  type="button"
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                  onFocus={() => setHover(i)}
                  onBlur={() => setHover(null)}
                  onClick={() => onSelect?.(i)}
                  aria-label={t('{label} : {value}', { label: d.sub || d.label, value: series.map((s) => `${s.label} ${formatValue(d.values[s.key] || 0)}`).join(', ') })}
                  className={`group relative flex h-full min-w-0 flex-1 items-end justify-center outline-none ${onSelect ? 'cursor-pointer' : 'cursor-default'}`}
                >
                  {active === i && <span className="absolute inset-y-0 inset-x-[2px] rounded-md bg-text/5" />}
                  <span
                    className="relative flex w-full max-w-6 flex-col-reverse gap-[2px] transition-opacity"
                    style={{ height: `${(total / max) * 100}%`, opacity: selected != null && selected !== i && hover == null ? 0.45 : 1 }}
                  >
                    {visible.map((s, j) => (
                      <span
                        key={s.key}
                        className={j === visible.length - 1 ? 'rounded-t-[4px]' : ''}
                        style={{ background: s.color, flexGrow: d.values[s.key], flexBasis: 0, minHeight: 2 }}
                      />
                    ))}
                  </span>
                </button>
              )
            })}
          </div>
          {/* Infobulle : la valeur d'abord, le nom de la série ensuite */}
          {active != null && data[active] && (
            <div
              className="pointer-events-none absolute z-10 min-w-36 -translate-x-1/2 rounded-xl border border-line bg-bg2 px-3 py-2 text-xs shadow-xl"
              style={{ left: `${((active + 0.5) / data.length) * 100}%`, bottom: `calc(${(totals[active] / max) * 100}% + 10px)` }}
            >
              <p className="mb-1 text-text2">{data[active].sub || data[active].label}</p>
              {series.map((s) => (
                <p key={s.key} className="flex items-center gap-2">
                  <span className="h-0.5 w-3 rounded" style={{ background: s.color }} />
                  <span className="font-semibold text-text">{formatValue(data[active].values[s.key] || 0)}</span>
                  <span className="text-text2">{s.label}</span>
                </p>
              ))}
            </div>
          )}
        </div>
      </div>
      {/* Axe des abscisses */}
      <div className="ml-12 mt-1.5 flex text-[10px] text-text3">
        {data.map((d, i) => (
          <span key={d.label + i} className="min-w-0 flex-1 truncate text-center">
            {i % labelEvery === 0 ? d.label : ''}
          </span>
        ))}
      </div>
    </div>
  )
}

/** Barres horizontales classées (une teinte), valeur au bout de la barre. */
export function RankedBars({ items, color = 'var(--series-1)', formatValue = fmt, onSelect }) {
  const max = Math.max(1, ...items.map((i) => i.value))
  const t = useT()
  return (
    <ul className="space-y-2">
      {items.map((it) => (
        <li key={it.label}>
          <button
            type="button"
            onClick={() => onSelect?.(it)}
            className={`grid w-full grid-cols-[minmax(0,9rem)_1fr] items-center gap-3 text-left text-xs ${onSelect ? 'hover:text-accent2' : 'cursor-default'}`}
            title={t('{label} : {value}', { label: it.label, value: formatValue(it.value) })}
          >
            <span className="truncate text-text2">{it.label}</span>
            <span className="flex items-center gap-2">
              <span className="h-3 rounded-r-[4px]" style={{ width: `${(it.value / max) * 100}%`, background: color, minWidth: 2 }} />
              <span className="shrink-0 font-medium tabular-nums text-text">{formatValue(it.value)}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}

/** Vue tableau : l'équivalent accessible de chaque graphique. */
export function DataTable({ columns, rows }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className="w-full text-xs">
        <thead className="bg-bg3 text-text2">
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={`px-3 py-2 font-medium ${c.numeric ? 'text-right' : 'text-left'}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line">
              {columns.map((c) => (
                <td key={c.key} className={`px-3 py-1.5 ${c.numeric ? 'text-right tabular-nums' : ''}`}>
                  {r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function StatTile({ label, value, sub }) {
  return (
    <div className="rounded-2xl border border-line bg-bg2 p-4">
      <p className="text-xs text-text2">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-text3">{sub}</p>}
    </div>
  )
}
