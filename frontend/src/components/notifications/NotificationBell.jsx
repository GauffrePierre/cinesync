import { useEffect, useRef, useState } from 'react'
import { Bell } from 'lucide-react'
import NotificationPanel from './NotificationPanel'
import { useNotifications } from '../../hooks/useMedia'
import { useT } from '../../i18n'

export default function NotificationBell() {
  const t = useT()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const { data } = useNotifications()
  const unread = data?.unread || 0

  useEffect(() => {
    if (!open) return
    const onClick = (e) => !ref.current?.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative rounded-full p-2 text-text2 hover:bg-bg3 hover:text-text"
        aria-label={unread ? t('Notifications ({n} non lues)', { n: unread }) : t('Notifications')}
      >
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-semibold text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>
      {open && <NotificationPanel items={data?.results || []} onClose={() => setOpen(false)} />}
    </div>
  )
}
