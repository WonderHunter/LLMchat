export function Logo({ className = 'size-7' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <rect width="32" height="32" rx="8" className="fill-accent" />
      <path
        d="M9 10.5A2.5 2.5 0 0 1 11.5 8h9a2.5 2.5 0 0 1 2.5 2.5v6a2.5 2.5 0 0 1-2.5 2.5H15l-4 4v-4.2A2.5 2.5 0 0 1 9 16.5z"
        className="fill-bg"
      />
    </svg>
  )
}
