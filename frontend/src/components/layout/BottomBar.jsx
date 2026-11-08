import { NavLink } from 'react-router'
import { useNavItems } from './nav'
import { useT } from '../../i18n'

// Navigation mobile : 6 ou 7 onglets (Bibliothèque seulement avec Plex), libellés courts
export default function BottomBar() {
  const t = useT()
  const items = useNavItems()
  return (
    <nav className="pb-safe fixed inset-x-0 bottom-0 z-40 border-t border-line bg-bg/85 backdrop-blur-xl md:hidden">
      <ul className={`grid ${{ 5: 'grid-cols-5', 6: 'grid-cols-6', 7: 'grid-cols-7' }[items.length] || 'grid-cols-7'}`}>
        {items.map(({ to, label, short, icon: Icon, end }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex flex-col items-center gap-1 pb-2 pt-2.5 text-[9px] font-medium transition ${isActive ? 'text-accent2' : 'text-text3'}`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className="h-[22px] w-[22px]" strokeWidth={isActive ? 2.2 : 1.8} />
                  <span className="max-w-full truncate px-0.5">{t(short || label)}</span>
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
