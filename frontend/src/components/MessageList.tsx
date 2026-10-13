import { Pencil, RefreshCw } from 'lucide-react'
import { memo, useState, type FormEvent, type KeyboardEvent } from 'react'
import type { Message } from '../api/types'
import { CopyButton } from './CopyButton'
import { Markdown } from './Markdown'

const actionButton = 'rounded-md p-1.5 transition-colors hover:bg-hover hover:text-text'

function EditForm({
  initial,
  onCancel,
  onSubmit,
}: {
  initial: string
  onCancel: () => void
  onSubmit: (text: string) => void
}) {
  const [draft, setDraft] = useState(initial)
  const text = draft.trim()

  function submit(event?: FormEvent) {
    event?.preventDefault()
    if (text) onSubmit(text)
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Escape') onCancel()
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={submit} className="rounded-3xl border border-accent bg-surface p-3">
      <textarea
        autoFocus
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onKeyDown}
        rows={Math.min(10, draft.split('\n').length + 1)}
        aria-label="Modifier le message"
        className="block w-full resize-none bg-transparent px-2 py-1 text-[15px] leading-relaxed outline-none"
      />
      <div className="mt-2 flex items-center gap-2">
        <span className="flex-1 px-2 text-xs text-muted">
          La suite de la conversation sera remplacée.
        </span>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-full px-3 py-1.5 text-sm hover:bg-hover"
        >
          Annuler
        </button>
        <button
          type="submit"
          disabled={!text || text === initial.trim()}
          className="rounded-full bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-40"
        >
          Envoyer
        </button>
      </div>
    </form>
  )
}

function UserBubble({ text, onEdit }: { text: string; onEdit?: (text: string) => void }) {
  const [editing, setEditing] = useState(false)

  if (editing && onEdit) {
    return (
      <EditForm
        initial={text}
        onCancel={() => setEditing(false)}
        onSubmit={(next) => {
          setEditing(false)
          onEdit(next)
        }}
      />
    )
  }

  return (
    <div className="group flex flex-col items-end gap-0.5">
      <div className="max-w-[85%] rounded-3xl bg-hover px-5 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap">
        {text}
      </div>
      {/* Visibles au survol ; toujours visibles au toucher, où le survol n'existe pas. */}
      <div className="flex text-muted opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100 max-md:opacity-100">
        <CopyButton text={text} label="Copier le message" />
        {onEdit && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            title="Modifier le message"
            aria-label="Modifier le message"
            className={actionButton}
          >
            <Pencil className="size-4" />
          </button>
        )}
      </div>
    </div>
  )
}

const shortModel = (model: string | null) => model?.split('/').pop() ?? ''

const integer = new Intl.NumberFormat('fr-FR')

function formatCost(cost: number): string {
  if (cost === 0) return 'gratuit'
  // Les petites réponses coûtent des fractions de centime : on garde assez de décimales.
  const digits = cost < 0.01 ? 4 : 2
  return `${cost.toLocaleString('fr-FR', { minimumFractionDigits: digits, maximumFractionDigits: digits })} $`
}

function Usage({ message }: { message: Message }) {
  if (message.input_tokens === null || message.output_tokens === null) return null
  const total = message.input_tokens + message.output_tokens
  const detail = `${integer.format(message.input_tokens)} tokens en entrée, ${integer.format(message.output_tokens)} en sortie`
  return (
    <span className="text-xs" title={detail}>
      · {integer.format(total)} tokens
      {message.cost !== null && ` · ${formatCost(message.cost)}`}
    </span>
  )
}

const MessageView = memo(function MessageView({
  message,
  onRegenerate,
  onEdit,
}: {
  message: Message
  onRegenerate?: () => void
  onEdit?: (messageId: number, text: string) => void
}) {
  if (message.role === 'user') {
    return (
      <UserBubble
        text={message.content}
        onEdit={onEdit && ((text) => onEdit(message.id, text))}
      />
    )
  }
  return (
    <div>
      <Markdown text={message.content} />
      <div className="mt-1 -ml-1.5 flex items-center gap-0.5 text-muted">
        <CopyButton text={message.content} label="Copier la réponse" />
        {onRegenerate && (
          <button
            type="button"
            onClick={onRegenerate}
            title="Régénérer la réponse"
            aria-label="Régénérer la réponse"
            className="rounded-md p-1.5 transition-colors hover:bg-hover hover:text-text"
          >
            <RefreshCw className="size-4" />
          </button>
        )}
        <span className="ml-1.5 text-xs">{shortModel(message.model)}</span>
        <Usage message={message} />
      </div>
    </div>
  )
})

function Thinking() {
  return (
    <div className="flex gap-1.5 py-2" role="status" aria-label="Réponse en cours">
      {[0, 1, 2].map((dot) => (
        <span
          key={dot}
          className="size-2 animate-bounce rounded-full bg-accent"
          style={{ animationDelay: `${dot * 120}ms` }}
        />
      ))}
    </div>
  )
}

interface MessageListProps {
  messages: Message[]
  /** Question envoyée mais pas encore enregistrée par le serveur. */
  pendingQuestion: string | null
  /** Texte de la réponse en cours ; null s'il n'y a pas de génération. */
  streamingText: string | null
  error: string | null
  onRegenerate?: () => void
  onEdit?: (messageId: number, text: string) => void
}

export function MessageList({
  messages,
  pendingQuestion,
  streamingText,
  error,
  onRegenerate,
  onEdit,
}: MessageListProps) {
  const idle = streamingText === null
  const last = messages[messages.length - 1]

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6">
      {messages.map((message) => (
        <MessageView
          key={message.id}
          message={message}
          onRegenerate={
            idle && message === last && message.role === 'assistant' ? onRegenerate : undefined
          }
          // Les messages provisoires (identifiant négatif) n'existent pas encore côté serveur.
          onEdit={idle && message.id > 0 ? onEdit : undefined}
        />
      ))}
      {pendingQuestion && <UserBubble text={pendingQuestion} />}
      {streamingText !== null &&
        (streamingText ? <Markdown text={streamingText} /> : <Thinking />)}
      {error && (
        <div
          role="alert"
          className="flex items-center gap-3 rounded-2xl border border-danger/40 bg-danger/5 px-4 py-3 text-sm text-danger"
        >
          <span className="flex-1">{error}</span>
          {idle && onRegenerate && last?.role === 'user' && (
            <button type="button" onClick={onRegenerate} className="font-medium hover:underline">
              Réessayer
            </button>
          )}
        </div>
      )}
    </div>
  )
}
