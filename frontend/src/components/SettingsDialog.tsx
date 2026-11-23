import { ExternalLink, X } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { useDeleteKey, useProviderKeys, useSaveKey, useSetFreeOnly } from '../api/hooks'
import type { KeyStatus } from '../api/types'
import { useChat } from '../chat/store'
import { AccountSettings } from './AccountSettings'

function ProviderRow({ status }: { status: KeyStatus }) {
  const [key, setKey] = useState('')
  const [editing, setEditing] = useState(false)
  const save = useSaveKey()
  const remove = useDeleteKey()
  const setFreeOnly = useSetFreeOnly()

  function submit(event: FormEvent) {
    event.preventDefault()
    save.mutate(
      { provider: status.provider, key },
      {
        onSuccess: () => {
          setKey('')
          setEditing(false)
        },
      },
    )
  }

  const showForm = !status.has_key || editing

  return (
    <section className="rounded-2xl border border-border p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-medium">{status.label}</h3>
        <a
          href={status.keys_url}
          target="_blank"
          rel="noreferrer noopener"
          className="inline-flex items-center gap-1 text-xs text-accent hover:underline"
        >
          Obtenir une clé <ExternalLink className="size-3" />
        </a>
      </div>

      {status.has_key && !editing && (
        <div className="mt-3 flex items-center gap-3 text-sm">
          <code className="rounded-md bg-code-bg px-2 py-1 font-mono text-xs">
            ••••••••{status.last4}
          </code>
          <span className="flex-1" />
          <button type="button" className="hover:underline" onClick={() => setEditing(true)}>
            Remplacer
          </button>
          <button
            type="button"
            className="text-danger hover:underline"
            disabled={remove.isPending}
            onClick={() => remove.mutate(status.provider)}
          >
            Supprimer
          </button>
        </div>
      )}

      {showForm && (
        <form onSubmit={submit} className="mt-3 flex gap-2">
          <input
            type="password"
            value={key}
            onChange={(event) => setKey(event.target.value)}
            placeholder={`Clé API ${status.label}`}
            aria-label={`Clé API ${status.label}`}
            autoComplete="off"
            spellCheck={false}
            className="min-w-0 flex-1 rounded-lg border border-border bg-bg px-3 py-2 font-mono text-sm outline-none focus:border-accent"
          />
          <button
            type="submit"
            disabled={key.trim().length < 8 || save.isPending}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-40"
          >
            {save.isPending ? 'Vérification…' : 'Enregistrer'}
          </button>
          {editing && (
            <button
              type="button"
              className="px-1 text-sm text-muted hover:underline"
              onClick={() => {
                setEditing(false)
                setKey('')
                save.reset()
              }}
            >
              Annuler
            </button>
          )}
        </form>
      )}
      {save.isError && <p className="mt-2 text-sm text-danger">{save.error.message}</p>}

      {status.has_key && status.free_only !== null && (
        <label className="mt-4 flex cursor-pointer items-start gap-3 border-t border-border pt-3 text-sm">
          <input
            type="checkbox"
            className="mt-0.5 size-4 accent-(--accent)"
            checked={status.free_only}
            disabled={setFreeOnly.isPending}
            onChange={(event) =>
              setFreeOnly.mutate({ provider: status.provider, freeOnly: event.target.checked })
            }
          />
          <span>
            Modèles gratuits uniquement
            <span className="block text-xs text-muted">
              Décochez pour voir aussi les modèles payants, facturés sur votre compte{' '}
              {status.label}.
            </span>
          </span>
        </label>
      )}
    </section>
  )
}

export function SettingsDialog() {
  const open = useChat((state) => state.settingsOpen)
  const setOpen = useChat((state) => state.setSettingsOpen)
  const { data: statuses } = useProviderKeys()

  const [tab, setTab] = useState<'keys' | 'account'>('keys')

  useEffect(() => {
    if (!open) return
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, setOpen])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4"
      onPointerDown={(event) => event.target === event.currentTarget && setOpen(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        className="flex max-h-full w-full max-w-xl flex-col rounded-3xl border border-border bg-surface shadow-2xl"
      >
        <header className="flex items-center justify-between px-6 pt-5 pb-3">
          <h2 id="settings-title" className="font-serif text-2xl">
            Réglages
          </h2>
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Fermer"
            className="rounded-md p-1.5 text-muted hover:bg-hover hover:text-text"
          >
            <X className="size-5" />
          </button>
        </header>
        <div className="mx-6 mb-4 flex self-start rounded-lg bg-hover p-0.5" role="tablist">
          {(['keys', 'account'] as const).map((name) => (
            <button
              key={name}
              type="button"
              role="tab"
              aria-selected={tab === name}
              onClick={() => setTab(name)}
              className={`rounded-md px-3 py-1 text-sm ${tab === name ? 'bg-surface font-medium shadow-sm' : 'text-muted hover:text-text'}`}
            >
              {name === 'keys' ? 'Clés API' : 'Compte'}
            </button>
          ))}
        </div>
        <div className="flex flex-col gap-3 overflow-y-auto px-6 pb-6">
          {tab === 'keys' ? (
            <>
              <p className="text-sm text-muted">
                Ajoutez la clé d'au moins un fournisseur. Chaque clé est vérifiée, chiffrée sur le
                serveur, et n'est plus jamais affichée ensuite.
              </p>
              {statuses?.map((status) => (
                <ProviderRow key={status.provider} status={status} />
              ))}
            </>
          ) : (
            <AccountSettings />
          )}
        </div>
      </div>
    </div>
  )
}
