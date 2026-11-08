import { useId } from 'react'

export default function Logo({ className = '' }) {
  // id unique : plusieurs logos coexistent (sidebar masquée + barre mobile)
  const gid = 'logo' + useId().replace(/:/g, '')
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden="true">
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#9d97ff" />
            <stop offset="1" stopColor="#6c63ff" />
          </linearGradient>
        </defs>
        <rect width="32" height="32" rx="9" fill={`url(#${gid})`} />
        <path d="M12 10.5v11l9.5-5.5z" fill="#fff" />
      </svg>
      <span className="text-lg font-semibold tracking-[-0.02em]">SynCiné</span>
    </span>
  )
}
