import { ArrowUp, FileText, LoaderCircle, Paperclip, Square, X } from 'lucide-react'
import {
  useEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type DragEvent,
  type KeyboardEvent,
} from 'react'
import { api, uploadFile } from '../api/client'
import type { Attachment } from '../api/types'

const MAX_FILES = 5
const ACCEPT =
  'image/png,image/jpeg,image/gif,image/webp,application/pdf,text/*,.md,.csv,.json,.yaml,.yml,.toml,.xml,.log,.sql,.py,.js,.ts,.tsx,.jsx,.html,.css,.sh'

interface PendingFile {
  key: string
  name: string
  /** Aperçu local d'une image, affiché avant même la fin de l'envoi. */
  previewUrl: string | null
  status: 'uploading' | 'ready' | 'error'
  attachment?: Attachment
  error?: string
}

interface ComposerProps {
  streaming: boolean
  disabled: boolean
  /** Le modèle choisi sait-il lire les images ? */
  acceptsImages: boolean
  /** Renvoie false si l'envoi a été refusé : le texte et les fichiers restent alors en place. */
  onSend: (text: string, attachments: Attachment[]) => Promise<boolean>
  onStop: () => void
}

export function Composer({ streaming, disabled, acceptsImages, onSend, onStop }: ComposerProps) {
  const [text, setText] = useState('')
  const [files, setFiles] = useState<PendingFile[]>([])
  const [dragging, setDragging] = useState(false)
  const textarea = useRef<HTMLTextAreaElement>(null)
  const picker = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const element = textarea.current
    if (!element) return
    element.style.height = 'auto'
    // Vide, la zone garde sa hauteur d'une ligne, quelle que soit la largeur au moment du calcul.
    if (text) element.style.height = `${Math.min(element.scrollHeight, 240)}px`
  }, [text])

  function patchFile(key: string, changes: Partial<PendingFile>) {
    setFiles((current) => current.map((file) => (file.key === key ? { ...file, ...changes } : file)))
  }

  function addFiles(selected: File[]) {
    const room = MAX_FILES - files.length
    for (const file of selected.slice(0, Math.max(room, 0))) {
      const key = crypto.randomUUID()
      const isImage = file.type.startsWith('image/')
      const entry: PendingFile = {
        key,
        name: file.name,
        previewUrl: isImage ? URL.createObjectURL(file) : null,
        status: 'uploading',
      }
      if (isImage && !acceptsImages) {
        setFiles((current) => [
          ...current,
          { ...entry, status: 'error', error: 'Ce modèle ne lit pas les images' },
        ])
        continue
      }
      setFiles((current) => [...current, entry])
      uploadFile(file)
        .then((attachment) => patchFile(key, { status: 'ready', attachment }))
        .catch((error: unknown) =>
          patchFile(key, {
            status: 'error',
            error: error instanceof Error ? error.message : 'Envoi impossible',
          }),
        )
    }
  }

  function removeFile(file: PendingFile) {
    if (file.previewUrl) URL.revokeObjectURL(file.previewUrl)
    setFiles((current) => current.filter((other) => other.key !== file.key))
    // Le serveur efface de toute façon les fichiers jamais envoyés : un échec ici est sans effet.
    if (file.attachment) {
      void api(`/api/attachments/${file.attachment.id}`, { method: 'DELETE' }).catch(() => {})
    }
  }

  const ready = files.flatMap((file) => (file.attachment ? [file.attachment] : []))
  const uploading = files.some((file) => file.status === 'uploading')
  // Des images déjà jointes, puis un changement vers un modèle qui ne les lit pas.
  const blockedImages = !acceptsImages && ready.some((attachment) => attachment.kind === 'image')
  const canSend =
    (text.trim() !== '' || ready.length > 0) && !disabled && !uploading && !blockedImages

  async function submit() {
    if (!canSend || streaming) return
    const content = text.trim()
    const sent = files
    setText('')
    setFiles([])
    const accepted = await onSend(content, ready)
    if (accepted) {
      for (const file of sent) if (file.previewUrl) URL.revokeObjectURL(file.previewUrl)
    } else {
      setText((current) => current || content)
      setFiles((current) => (current.length > 0 ? current : sent))
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      void submit()
    }
  }

  function onPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const pasted = [...event.clipboardData.files]
    if (pasted.length === 0) return
    event.preventDefault()
    addFiles(pasted)
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    addFiles([...event.dataTransfer.files])
  }

  let hint = 'PDF et fichiers texte acceptés (ce modèle ne lit pas les images)'
  if (acceptsImages) hint = 'Images, PDF et fichiers texte acceptés'
  if (blockedImages) hint = 'Ce modèle ne lit pas les images : retirez-les ou changez de modèle.'

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={`rounded-3xl border bg-surface shadow-sm transition-shadow focus-within:shadow-md ${dragging ? 'border-accent' : 'border-border'}`}
    >
      {files.length > 0 && (
        <ul className="flex flex-wrap gap-2 px-4 pt-4" aria-label="Pièces jointes">
          {files.map((file) => (
            <li
              key={file.key}
              title={file.error ?? file.name}
              className={`relative flex items-center gap-2 rounded-xl border text-sm ${file.status === 'error' ? 'border-danger/50 text-danger' : 'border-border'} ${file.previewUrl ? 'p-1 pr-7' : 'py-1.5 pr-7 pl-2.5'}`}
            >
              {file.previewUrl ? (
                <img src={file.previewUrl} alt="" className="size-12 rounded-lg object-cover" />
              ) : (
                <FileText className="size-4 shrink-0" />
              )}
              <span className="flex max-w-40 flex-col">
                <span className="truncate">{file.name}</span>
                {file.error && <span className="truncate text-xs">{file.error}</span>}
              </span>
              {file.status === 'uploading' && (
                <LoaderCircle
                  className="size-4 shrink-0 animate-spin text-muted"
                  aria-label="Envoi en cours"
                />
              )}
              <button
                type="button"
                onClick={() => removeFile(file)}
                aria-label={`Retirer ${file.name}`}
                className="absolute top-1 right-1 rounded-full p-0.5 text-muted hover:bg-hover hover:text-text"
              >
                <X className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <textarea
        ref={textarea}
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={onKeyDown}
        onPaste={onPaste}
        rows={1}
        autoFocus
        placeholder="Écrire un message…"
        aria-label="Message"
        className="block w-full resize-none bg-transparent px-5 pt-4 pb-1 text-[15px] leading-relaxed outline-none placeholder:text-muted"
      />

      <div className="flex items-center gap-2 px-3 pb-3">
        <input
          ref={picker}
          type="file"
          multiple
          hidden
          accept={ACCEPT}
          onChange={(event) => {
            addFiles([...(event.target.files ?? [])])
            event.target.value = ''
          }}
        />
        <button
          type="button"
          onClick={() => picker.current?.click()}
          disabled={disabled || files.length >= MAX_FILES}
          title="Joindre des fichiers"
          aria-label="Joindre des fichiers"
          className="flex size-9 shrink-0 items-center justify-center rounded-full text-muted transition-colors hover:bg-hover hover:text-text disabled:opacity-40"
        >
          <Paperclip className="size-5" />
        </button>
        <span
          className={`min-w-0 flex-1 truncate text-xs ${blockedImages ? 'text-danger' : 'text-muted'}`}
        >
          {hint}
        </span>
        {streaming ? (
          <button
            type="button"
            onClick={onStop}
            title="Arrêter la génération"
            aria-label="Arrêter la génération"
            className="flex size-9 shrink-0 items-center justify-center rounded-full bg-text text-bg transition-opacity hover:opacity-80"
          >
            <Square className="size-3.5 fill-current" />
          </button>
        ) : (
          <button
            type="button"
            onClick={() => void submit()}
            disabled={!canSend}
            title="Envoyer"
            aria-label="Envoyer"
            className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ArrowUp className="size-5" />
          </button>
        )}
      </div>
    </div>
  )
}
