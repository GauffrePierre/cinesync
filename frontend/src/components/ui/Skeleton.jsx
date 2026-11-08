export default function Skeleton({ className = '' }) {
  return <div className={`skeleton rounded-xl ${className}`} />
}

export function CardSkeleton({ fluid = false }) {
  return (
    <div className={fluid ? 'w-full' : 'w-[132px] shrink-0 md:w-[156px]'}>
      <Skeleton className="aspect-[2/3] w-full rounded-2xl" />
      <Skeleton className="mt-2 h-3.5 w-4/5" />
      <Skeleton className="mt-1.5 h-3 w-1/2" />
    </div>
  )
}
