import { Link } from 'react-router'
import { Sparkles } from 'lucide-react'
import { useT } from '../../i18n'

export default function MockBanner({ service = 'TMDB', show = true }) {
  const t = useT()
  if (!show) return null
  // Le nom du service est mis en valeur : la phrase traduite est coupée autour de {service}
  const [before, after = ''] = t('Données de démonstration — configure {service} dans le Profil pour voir tes vraies données.').split('{service}')
  return (
    <Link
      to="/profile"
      className="mb-6 flex items-center gap-3 rounded-2xl border border-accent/30 bg-accent/10 px-4 py-3 text-sm text-text hover:bg-accent/15"
    >
      <Sparkles className="h-4 w-4 shrink-0 text-accent2" />
      <span>
        {before}
        <span className="font-medium">{service}</span>
        {after}
      </span>
    </Link>
  )
}
