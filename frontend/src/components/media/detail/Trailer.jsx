import { useState } from 'react'
import { Play } from 'lucide-react'
import { useT } from '../../../i18n'

// Bande-annonce YouTube : chargée seulement au clic (vie privée + performance)
export default function Trailer({ trailer, backdrop }) {
  const t = useT()
  const [playing, setPlaying] = useState(false)
  if (!trailer) return null
  return (
    <section className="mb-10" id="trailer">
      <h2 className="mb-4 text-lg font-semibold">{t('Bande-annonce')}</h2>
      <div className="relative aspect-video overflow-hidden rounded-2xl bg-black">
        {playing ? (
          <iframe
            className="absolute inset-0 h-full w-full"
            src={`https://www.youtube-nocookie.com/embed/${trailer.key}?autoplay=1&rel=0`}
            title={trailer.name || t('Bande-annonce')}
            allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
            allowFullScreen
          />
        ) : (
          <button onClick={() => setPlaying(true)} className="group absolute inset-0" aria-label={t('Lire la bande-annonce')}>
            <img
              src={`https://i.ytimg.com/vi/${trailer.key}/hqdefault.jpg`}
              onError={(e) => backdrop && (e.currentTarget.src = backdrop)}
              alt=""
              className="h-full w-full object-cover opacity-80 transition group-hover:opacity-100"
            />
            <span className="absolute inset-0 flex items-center justify-center">
              <span className="flex h-16 w-16 items-center justify-center rounded-full bg-white/20 backdrop-blur-md transition group-hover:scale-110">
                <Play className="ml-1 h-7 w-7 fill-white text-white" />
              </span>
            </span>
            <span className="absolute bottom-3 left-4 text-sm font-medium text-white drop-shadow">{trailer.name}</span>
          </button>
        )}
      </div>
    </section>
  )
}
