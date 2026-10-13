import { streamSSE } from '../api/client'
import { keys, queryClient } from '../api/hooks'
import type { Conversation, ConversationDetail, Message, Selection } from '../api/types'
import { useChat } from './store'

let controller: AbortController | null = null

function withoutTrailingReplies(messages: Message[]): Message[] {
  const kept = [...messages]
  while (kept.length > 0 && kept[kept.length - 1].role === 'assistant') kept.pop()
  return kept
}

/** Les messages qui précèdent celui-ci (tous, s'il est introuvable). */
function upTo(messages: Message[], messageId: number): Message[] {
  const index = messages.findIndex((message) => message.id === messageId)
  return index === -1 ? messages : messages.slice(0, index)
}

function appendMessage(conversationId: string, message: Message) {
  queryClient.setQueryData<ConversationDetail>(keys.conversation(conversationId), (current) =>
    current ? { ...current, messages: [...current.messages, message] } : current,
  )
}

/**
 * Lance une génération et tient l'interface à jour pendant le flux.
 * Renvoie false si le serveur a refusé la requête avant de commencer à répondre.
 */
async function run(
  path: string,
  body: unknown,
  conversationId: string | null,
  question: string | null,
  onCreated?: (id: string) => void,
): Promise<boolean> {
  controller = new AbortController()
  useChat.setState({ stream: { conversationId, question, text: '' }, error: null })
  let currentId = conversationId
  let started = false

  try {
    await streamSSE(
      path,
      body,
      (event, data) => {
        if (event === 'start') {
          started = true
          const conversation = data.conversation as Conversation
          const userMessage = data.user_message as Message | null
          const edited = (data.edited_message ?? null) as Message | null
          currentId = conversation.id
          const known =
            queryClient.getQueryData<ConversationDetail>(keys.conversation(conversation.id))
              ?.messages ?? []
          let messages: Message[]
          if (userMessage) messages = [...known, userMessage]
          else if (edited) messages = [...upTo(known, edited.id), edited]
          else messages = withoutTrailingReplies(known)
          queryClient.setQueryData<ConversationDetail>(keys.conversation(conversation.id), {
            ...conversation,
            messages,
          })
          useChat.setState({ stream: { conversationId: conversation.id, question: null, text: '' } })
          void queryClient.invalidateQueries({ queryKey: keys.conversations })
          if (!conversationId) onCreated?.(conversation.id)
        } else if (event === 'delta') {
          useChat.setState((state) => ({
            stream: state.stream && { ...state.stream, text: state.stream.text + (data.text as string) },
          }))
        } else if (event === 'error') {
          useChat.setState({
            error: { conversationId: currentId, message: data.message as string },
          })
        } else if (event === 'done' && data.message && currentId) {
          appendMessage(currentId, data.message as Message)
          // Dans le même rendu, pour ne pas afficher la réponse en double.
          useChat.setState({ stream: null })
        }
      },
      controller.signal,
    )
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      // Arrêt demandé : on garde le texte reçu, puis on se cale sur ce que le serveur a enregistré.
      const partial = useChat.getState().stream?.text
      if (currentId && partial) {
        const { selection } = useChat.getState()
        appendMessage(currentId, {
          id: -Date.now(),
          role: 'assistant',
          content: partial,
          provider: selection?.provider ?? null,
          model: selection?.model ?? null,
          input_tokens: null,
          output_tokens: null,
          cost: null,
          created_at: new Date().toISOString(),
        })
      }
      const stoppedId = currentId
      if (stoppedId) {
        setTimeout(() => {
          void queryClient.invalidateQueries({ queryKey: keys.conversation(stoppedId) })
        }, 800)
      }
    } else {
      const message = error instanceof Error ? error.message : 'Connexion au serveur impossible.'
      useChat.setState({ error: { conversationId: currentId, message } })
    }
  } finally {
    controller = null
    useChat.setState({ stream: null })
    void queryClient.invalidateQueries({ queryKey: keys.conversations })
  }
  return started
}

export function sendMessage(
  conversationId: string | null,
  content: string,
  selection: Selection,
  onCreated: (id: string) => void,
): Promise<boolean> {
  const body = { conversation_id: conversationId, content, ...selection }
  return run('/api/chat', body, conversationId, content, onCreated)
}

export async function regenerate(conversationId: string, selection: Selection): Promise<void> {
  const key = keys.conversation(conversationId)
  // L'ancienne réponse disparaît tout de suite ; on la retrouve si le serveur refuse.
  queryClient.setQueryData<ConversationDetail>(key, (current) =>
    current ? { ...current, messages: withoutTrailingReplies(current.messages) } : current,
  )
  const started = await run(
    `/api/conversations/${conversationId}/regenerate`,
    selection,
    conversationId,
    null,
  )
  if (!started) void queryClient.invalidateQueries({ queryKey: key })
}

/** Réécrit une question : tout ce qui la suivait est remplacé par une nouvelle réponse. */
export async function editMessage(
  conversationId: string,
  messageId: number,
  content: string,
  selection: Selection,
): Promise<void> {
  const key = keys.conversation(conversationId)
  queryClient.setQueryData<ConversationDetail>(key, (current) => {
    const original = current?.messages.find((message) => message.id === messageId)
    if (!current || !original) return current
    return { ...current, messages: [...upTo(current.messages, messageId), { ...original, content }] }
  })
  const started = await run(
    `/api/conversations/${conversationId}/messages/${messageId}/edit`,
    { content, ...selection },
    conversationId,
    null,
  )
  if (!started) void queryClient.invalidateQueries({ queryKey: key })
}

export function stopStreaming() {
  controller?.abort()
}
