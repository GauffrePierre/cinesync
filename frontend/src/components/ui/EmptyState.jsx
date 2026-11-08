import { Link } from 'react-router'

export default function EmptyState({ icon: Icon, title, message, action, to }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-3xl border border-dashed border-line px-6 py-14 text-center">
      {Icon && (
        <div className="mb-4 rounded-2xl bg-bg3 p-3 text-text2">
          <Icon className="h-6 w-6" />
        </div>
      )}
      <p className="font-medium">{title}</p>
      {message && <p className="mt-1 max-w-sm text-sm text-text2">{message}</p>}
      {action && to && (
        <Link to={to} className="mt-5 rounded-xl bg-accent px-4 py-2 text-sm font-medium text-white hover:brightness-110">
          {action}
        </Link>
      )}
    </div>
  )
}
