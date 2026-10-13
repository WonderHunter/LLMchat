import { ArrowUp, Square } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent } from 'react'

interface ComposerProps {
  streaming: boolean
  disabled: boolean
  /** Renvoie false si l'envoi a été refusé : le texte est alors remis dans la zone de saisie. */
  onSend: (text: string) => Promise<boolean>
  onStop: () => void
}

export function Composer({ streaming, disabled, onSend, onStop }: ComposerProps) {
  const [text, setText] = useState('')
  const textarea = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const element = textarea.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, 240)}px`
  }, [text])

  async function submit() {
    const content = text.trim()
    if (!content || streaming || disabled) return
    setText('')
    const accepted = await onSend(content)
    if (!accepted) setText((current) => current || content)
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      void submit()
    }
  }

  return (
    <div className="rounded-3xl border border-border bg-surface shadow-sm transition-shadow focus-within:shadow-md">
      <textarea
        ref={textarea}
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={onKeyDown}
        rows={1}
        autoFocus
        placeholder="Écrire un message…"
        aria-label="Message"
        className="block w-full resize-none bg-transparent px-5 pt-4 pb-1 text-[15px] leading-relaxed outline-none placeholder:text-muted"
      />
      <div className="flex items-center justify-between px-3 pb-3">
        <span className="pl-2 text-xs text-muted max-sm:invisible">Entrée pour envoyer, Maj + Entrée pour un saut de ligne</span>
        {streaming ? (
          <button
            type="button"
            onClick={onStop}
            title="Arrêter la génération"
            aria-label="Arrêter la génération"
            className="flex size-9 items-center justify-center rounded-full bg-text text-bg transition-opacity hover:opacity-80"
          >
            <Square className="size-3.5 fill-current" />
          </button>
        ) : (
          <button
            type="button"
            onClick={() => void submit()}
            disabled={!text.trim() || disabled}
            title="Envoyer"
            aria-label="Envoyer"
            className="flex size-9 items-center justify-center rounded-full bg-accent text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ArrowUp className="size-5" />
          </button>
        )}
      </div>
    </div>
  )
}
