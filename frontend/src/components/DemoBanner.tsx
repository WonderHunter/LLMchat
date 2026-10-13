import { FlaskConical } from 'lucide-react'
import { useAuthConfig } from '../api/hooks'

/** Prévient que le serveur est celui de démonstration : rien n'y est réel. */
export function DemoBanner() {
  const { data: config } = useAuthConfig()
  if (!config?.demo) return null
  return (
    <p
      role="status"
      className="flex shrink-0 items-center justify-center gap-2 bg-accent-soft px-4 py-1.5 text-center text-xs text-accent"
    >
      <FlaskConical className="size-3.5 shrink-0" />
      Mode démonstration : les réponses sont simulées et seules les clés commençant par « demo- »
      sont acceptées. Vos vraies clés ne fonctionneront pas ici.
    </p>
  )
}
