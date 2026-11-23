const mask = 'url(/logo-mark.png) center / contain no-repeat'

/** Le logo, teinté à la couleur d'accent du thème (le fichier ne sert que de masque). */
export function Logo({ className = 'size-8' }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block shrink-0 bg-accent ${className}`}
      style={{ mask, WebkitMask: mask }}
    />
  )
}
