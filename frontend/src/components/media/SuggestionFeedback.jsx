import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ThumbsDown, ThumbsUp } from 'lucide-react'
import { media } from '../../services/tmdb'
import { toast } from '../../store/uiStore'
import { useT } from '../../i18n'

// Sous une suggestion : « Plus comme ça » / « Moins comme ça ». Le titre sert ensuite de référence (positive ou
// négative) et quitte la liste, qui se recalcule aussitôt.
export default function SuggestionFeedback({ item }) {
  const t = useT()
  const qc = useQueryClient()
  const send = useMutation({
    mutationFn: (value) => media.suggestionFeedback(item, value),
    onSuccess: (_, value) => {
      toast(value > 0 ? t('Noté : plus de titres comme {title}', { title: item.title }) : t('Noté : moins de titres comme {title}', { title: item.title }), 'success')
      qc.invalidateQueries({ queryKey: ['suggestions'] })
    },
    onError: (e) => toast(e.message, 'error'),
  })
  // Dans la carte (qui ouvre la fiche au clic) : le clic sur un bouton ne doit pas l'ouvrir
  const vote = (e, value) => {
    e.preventDefault()
    e.stopPropagation()
    send.mutate(value)
  }
  const btn = 'flex h-7 flex-1 items-center justify-center gap-1 rounded-lg border border-line text-[11px] text-text2 transition hover:bg-bg3 hover:text-text disabled:opacity-50'
  return (
    <div className="mt-1">
      {item.why && <p className="line-clamp-2 text-[11px] leading-snug text-accent2">{item.why}</p>}
      <div className="mt-1.5 flex gap-1.5">
      <button type="button" className={btn} disabled={send.isPending} onClick={(e) => vote(e, 1)} title={t('Plus comme ça')} aria-label={t('Plus comme ça')}>
        <ThumbsUp className="h-3.5 w-3.5" />
      </button>
      <button type="button" className={btn} disabled={send.isPending} onClick={(e) => vote(e, -1)} title={t('Moins comme ça')} aria-label={t('Moins comme ça')}>
        <ThumbsDown className="h-3.5 w-3.5" />
      </button>
      </div>
    </div>
  )
}
