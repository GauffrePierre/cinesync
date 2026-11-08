import Modal from '../ui/Modal'
import StarRating from '../ui/StarRating'
import { useT } from '../../i18n'

// « Déjà vu » : demande une note (1-5) avant l'envoi à Trakt
export default function RatingModal({ item, onRate, onClose }) {
  const t = useT()
  const [pre, post] = t('Quelle note pour {title} ?').split('{title}')
  return (
    <Modal open={!!item} onClose={onClose} title={t("Tu l'as déjà vu ?")}>
      {item && (
        <div className="flex flex-col items-center gap-5 py-2 text-center">
          <p className="text-sm text-text2">
            {pre}<span className="font-medium text-text">{item.title}</span>{post}
          </p>
          <StarRating size="lg" onChange={(stars) => onRate(stars)} />
          <button onClick={() => onRate(null)} className="text-sm text-text2 hover:text-text">
            {t('Marquer vu sans noter')}
          </button>
        </div>
      )}
    </Modal>
  )
}
