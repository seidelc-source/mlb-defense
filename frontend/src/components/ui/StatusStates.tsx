interface EmptyProps {
  message: string
  icon?: string
}

export function EmptyState({ message, icon = '—' }: EmptyProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-[color:var(--muted)]">
      <span className="text-3xl mb-2">{icon}</span>
      <p className="text-sm">{message}</p>
    </div>
  )
}

export function LoadingState({ message = 'Loading...' }: { message?: string }) {
  return (
    <div className="flex items-center gap-2 py-8 px-4 text-[color:var(--muted)] text-sm animate-pulse">
      <div className="w-4 h-4 border-2 border-[color:var(--line)] border-t-[color:var(--muted)] rounded-full animate-spin" />
      {message}
    </div>
  )
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-md px-4 py-3 text-sm bg-[#f6e3e3] border border-[#e4b9b9] text-[color:var(--danger)]">
      {message}
    </div>
  )
}
