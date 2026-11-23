import { useEffect, useMemo } from 'react'
import { useModels } from '../api/hooks'
import type { ModelInfo } from '../api/types'
import { useChat } from './store'

export interface ModelChoice {
  provider: string
  providerLabel: string
  model: ModelInfo
}

/** Le modèle choisi, ramené à un modèle disponible si le choix mémorisé ne l'est plus. */
export function useSelection() {
  const { data: providers } = useModels()
  const selection = useChat((state) => state.selection)
  const setSelection = useChat((state) => state.setSelection)

  const choices = useMemo<ModelChoice[]>(
    () =>
      (providers ?? []).flatMap((entry) =>
        entry.models.map((model) => ({
          provider: entry.provider,
          providerLabel: entry.label,
          model,
        })),
      ),
    [providers],
  )
  const current = choices.find(
    (choice) => choice.provider === selection?.provider && choice.model.id === selection?.model,
  )

  useEffect(() => {
    if (!providers || current || choices.length === 0) return
    const fallback = choices.find((choice) => choice.model.free) ?? choices[0]
    setSelection({ provider: fallback.provider, model: fallback.model.id })
  }, [providers, current, choices, setSelection])

  return {
    providers: providers ?? [],
    loaded: providers !== undefined,
    choices,
    current,
    selection: current ? { provider: current.provider, model: current.model.id } : null,
  }
}
