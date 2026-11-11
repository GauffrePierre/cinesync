import { createContext, useContext } from 'react'

// Recherche dans les réglages : une rubrique s'affiche si son titre, sa description ou ses mots-clés
// (français et anglais) contiennent le texte cherché
export const SearchContext = createContext('')
export const fold = (s) => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()

export default function Section({ title, description, keywords = '', children, right, className = '' }) {
  const query = useContext(SearchContext)
  if (query && !fold(`${title} ${description || ''} ${keywords}`).includes(query)) return null
  return (
    <section className={`mb-10 ${className}`}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">{title}</h2>
        {right}
      </div>
      {description && <p className="mb-4 mt-0.5 text-sm text-text2">{description}</p>}
      {!description && <div className="mb-4" />}
      {children}
    </section>
  )
}
