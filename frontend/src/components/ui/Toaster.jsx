import { AnimatePresence, motion } from 'motion/react'
import { CheckCircle2, AlertCircle, Info } from 'lucide-react'
import { useUiStore } from '../../store/uiStore'

const ICONS = { success: CheckCircle2, error: AlertCircle, info: Info }
const COLORS = { success: 'text-emerald-400', error: 'text-red-400', info: 'text-accent2' }

export default function Toaster() {
  const toasts = useUiStore((s) => s.toasts)
  const dismiss = useUiStore((s) => s.dismissToast)
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-24 z-[70] flex flex-col items-center gap-2 px-4 lg:bottom-6">
      <AnimatePresence>
        {toasts.map((t) => {
          const Icon = ICONS[t.kind] || Info
          return (
            <motion.button
              key={t.id}
              layout
              initial={{ opacity: 0, y: 16, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.96 }}
              onClick={() => dismiss(t.id)}
              className="pointer-events-auto flex max-w-md items-center gap-2.5 rounded-2xl border border-line bg-bg2/95 px-4 py-3 text-left text-sm shadow-xl backdrop-blur-xl"
            >
              <Icon className={`h-4 w-4 shrink-0 ${COLORS[t.kind]}`} />
              <span>{t.message}</span>
            </motion.button>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
