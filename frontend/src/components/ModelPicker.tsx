import { Check, ChevronDown, Image as ImageIcon, Search } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { ModelInfo } from '../api/types'
import { useChat } from '../chat/store'
import { useSelection } from '../chat/useSelection'

function price(model: ModelInfo): string | undefined {
  if (model.input_price === null || model.output_price === null) return undefined
  return `${model.input_price} $ en entrée, ${model.output_price} $ en sortie, par million de tokens`
}

function Badge({ free }: { free: boolean }) {
  return free ? (
    <span className="rounded-full bg-success-soft px-2 py-0.5 text-[11px] font-medium text-success">
      Gratuit
    </span>
  ) : (
    <span className="rounded-full bg-hover px-2 py-0.5 text-[11px] font-medium text-muted">
      Payant
    </span>
  )
}

export function ModelPicker() {
  const { providers, loaded, current } = useSelection()
  const setSelection = useChat((state) => state.setSelection)
  const setSettingsOpen = useChat((state) => state.setSettingsOpen)
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onPointerDown(event: PointerEvent) {
      if (!container.current?.contains(event.target as Node)) setOpen(false)
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  if (!loaded) return <div className="h-9" />

  if (providers.length === 0) {
    return (
      <button
        type="button"
        onClick={() => setSettingsOpen(true)}
        className="rounded-lg px-3 py-2 text-sm font-medium text-accent hover:bg-hover"
      >
        Ajouter une clé API
      </button>
    )
  }

  const needle = search.trim().toLowerCase()
  const groups = providers.map((entry) => ({
    ...entry,
    models: entry.models.filter(
      (model) =>
        !needle ||
        model.name.toLowerCase().includes(needle) ||
        model.id.toLowerCase().includes(needle),
    ),
  }))

  return (
    <div ref={container} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex max-w-[70vw] items-center gap-1.5 rounded-lg px-3 py-2 text-[15px] font-medium hover:bg-hover"
      >
        <span className="truncate">{current?.model.name ?? 'Choisir un modèle'}</span>
        <ChevronDown className="size-4 shrink-0 text-muted" />
      </button>

      {open && (
        <div className="absolute top-full left-0 z-20 mt-1 flex max-h-[min(30rem,70vh)] w-[min(26rem,90vw)] flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-xl">
          <label className="flex items-center gap-2 border-b border-border px-4 py-2.5">
            <Search className="size-4 text-muted" />
            <input
              autoFocus
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Rechercher un modèle"
              className="w-full bg-transparent text-sm outline-none placeholder:text-muted"
            />
          </label>
          <div className="overflow-y-auto p-1.5" role="listbox">
            {groups.map((group) => (
              <div key={group.provider} className="mb-1">
                <div className="px-3 pt-2 pb-1 text-xs font-semibold tracking-wide text-muted uppercase">
                  {group.label}
                </div>
                {group.error && <p className="px-3 py-1.5 text-sm text-danger">{group.error}</p>}
                {!group.error && group.models.length === 0 && (
                  <p className="px-3 py-1.5 text-sm text-muted">Aucun modèle</p>
                )}
                {group.models.map((model) => {
                  const selected =
                    current?.provider === group.provider && current.model.id === model.id
                  return (
                    <button
                      key={model.id}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      title={price(model)}
                      onClick={() => {
                        setSelection({ provider: group.provider, model: model.id })
                        setOpen(false)
                        setSearch('')
                      }}
                      className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-hover"
                    >
                      <span className="min-w-0 flex-1 truncate">{model.name}</span>
                      {model.accepts_images && (
                        <span title="Lit les images" className="shrink-0 text-muted">
                          <ImageIcon className="size-4" aria-label="Lit les images" />
                        </span>
                      )}
                      <Badge free={model.free} />
                      <Check
                        className={`size-4 shrink-0 text-accent ${selected ? '' : 'invisible'}`}
                      />
                    </button>
                  )
                })}
              </div>
            ))}
          </div>
          <p className="flex items-center gap-1.5 border-t border-border px-4 py-2 text-xs text-muted">
            <ImageIcon className="size-3.5" aria-hidden="true" />
            Le modèle lit les images jointes
          </p>
        </div>
      )}
    </div>
  )
}
