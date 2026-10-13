import { RefreshCw } from 'lucide-react'
import { memo } from 'react'
import type { Message } from '../api/types'
import { CopyButton } from './CopyButton'
import { Markdown } from './Markdown'

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-3xl bg-hover px-5 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap">
        {text}
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
}: {
  message: Message
  onRegenerate?: () => void
}) {
  if (message.role === 'user') return <UserBubble text={message.content} />
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
}

export function MessageList({
  messages,
  pendingQuestion,
  streamingText,
  error,
  onRegenerate,
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
