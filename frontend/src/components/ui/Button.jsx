import { Loader2 } from 'lucide-react'

const VARIANTS = {
  primary: 'bg-accent text-white hover:brightness-110',
  secondary: 'bg-bg3 text-text hover:bg-bg3/70 border border-line',
  ghost: 'text-text2 hover:text-text hover:bg-bg3',
  glass: 'bg-white/15 text-white backdrop-blur-md hover:bg-white/25 border border-white/10',
  danger: 'bg-red-500/10 text-red-500 hover:bg-red-500/20',
}

const SIZES = {
  sm: 'h-8 px-3 text-xs gap-1.5',
  md: 'h-10 px-4 text-sm gap-2',
  lg: 'h-12 px-5 text-sm gap-2',
  icon: 'h-10 w-10 justify-center',
}

export default function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  icon: Icon,
  className = '',
  children,
  disabled,
  ...props
}) {
  return (
    <button
      className={`inline-flex shrink-0 items-center rounded-xl font-medium transition duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/25 active:translate-y-0 active:scale-[0.97] disabled:pointer-events-none disabled:opacity-50 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : Icon ? <Icon className="h-4 w-4" /> : null}
      {children}
    </button>
  )
}
