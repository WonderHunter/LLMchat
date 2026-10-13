import { KeyRound, PanelLeftOpen } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useConversation, useMe } from '../api/hooks'
import { regenerate, sendMessage, stopStreaming } from '../chat/actions'
import { useChat } from '../chat/store'
import { useSelection } from '../chat/useSelection'
import { ArtifactPanel } from '../components/ArtifactPanel'
import { Composer } from '../components/Composer'
import { Logo } from '../components/Logo'
import { MessageList } from '../components/MessageList'
import { ModelPicker } from '../components/ModelPicker'
import { SettingsDialog } from '../components/SettingsDialog'
import { Sidebar } from '../components/Sidebar'

const isNarrow = () => window.innerWidth < 768

function greeting(email: string | undefined): string {
  const hello = new Date().getHours() >= 18 ? 'Bonsoir' : 'Bonjour'
  const name = email?.split('@')[0].split(/[._-]/)[0] ?? ''
  return name ? `${hello}, ${name[0].toUpperCase()}${name.slice(1)}` : hello
}

export function ChatPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: user } = useMe()
  const { data: conversation, isError: notFound } = useConversation(id)
  const { selection, loaded, providers } = useSelection()
  const stream = useChat((state) => state.stream)
  const error = useChat((state) => state.error)
  const sidebarOpen = useChat((state) => state.sidebarOpen)
  const toggleSidebar = useChat((state) => state.toggleSidebar)
  const setSelection = useChat((state) => state.setSelection)
  const setSettingsOpen = useChat((state) => state.setSettingsOpen)
  const setArtifact = useChat((state) => state.setArtifact)

  // En ouvrant une conversation, on reprend le modèle avec lequel elle a été menée.
  const conversationId = conversation?.id
  const conversationProvider = conversation?.provider
  const conversationModel = conversation?.model
  useEffect(() => {
    if (conversationId && conversationProvider && conversationModel) {
      setSelection({ provider: conversationProvider, model: conversationModel })
    }
    // Uniquement au changement de conversation, pas à chaque changement de modèle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId])

  useEffect(() => {
    if (notFound) navigate('/', { replace: true })
  }, [notFound, navigate])

  // En changeant de conversation : le panneau se ferme et, sur petit écran, la barre latérale aussi.
  useEffect(() => {
    setArtifact(null)
    if (isNarrow() && useChat.getState().sidebarOpen) toggleSidebar()
  }, [id, setArtifact, toggleSidebar])

  // La génération en cours ne s'affiche que dans la conversation qu'elle concerne.
  const here = stream !== null && stream.conversationId === (id ?? null)
  const messages = conversation?.messages ?? []
  const visibleError = error && error.conversationId === (id ?? null) ? error.message : null
  const empty = messages.length === 0 && !here

  // Suit le bas de la conversation, sauf si l'utilisateur est remonté lire plus haut.
  const scroller = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)
  useEffect(() => {
    pinned.current = true
  }, [id])
  useEffect(() => {
    const element = scroller.current
    if (element && pinned.current) element.scrollTop = element.scrollHeight
  }, [messages.length, stream?.text, stream?.question, visibleError])

  const hasModels = providers.some((entry) => entry.models.length > 0)

  const composer =
    loaded && !hasModels ? (
      <div className="flex flex-col items-center gap-3 rounded-3xl border border-border bg-surface px-6 py-6 text-center">
        <KeyRound className="size-6 text-accent" />
        <p className="text-sm text-muted">
          Ajoutez une clé OpenRouter, OpenAI ou Anthropic pour commencer à discuter.
        </p>
        <button
          type="button"
          onClick={() => setSettingsOpen(true)}
          className="rounded-full bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover"
        >
          Ajouter une clé API
        </button>
      </div>
    ) : (
      <Composer
        key={id ?? 'new'}
        streaming={stream !== null}
        disabled={!selection}
        onStop={stopStreaming}
        onSend={(text) =>
          selection
            ? sendMessage(id ?? null, text, selection, (newId) =>
                navigate(`/c/${newId}`, { replace: true }),
              )
            : Promise.resolve(false)
        }
      />
    )

  return (
    <div className="flex h-full">
      {sidebarOpen && (
        <>
          <div
            className="fixed inset-0 z-20 bg-black/40 md:hidden"
            onClick={toggleSidebar}
            aria-hidden="true"
          />
          <Sidebar />
        </>
      )}
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-1 px-3">
          {!sidebarOpen && (
            <button
              type="button"
              onClick={toggleSidebar}
              title="Afficher la barre latérale"
              aria-label="Afficher la barre latérale"
              className="rounded-md p-1.5 text-muted hover:bg-hover hover:text-text"
            >
              <PanelLeftOpen className="size-5" />
            </button>
          )}
          <ModelPicker />
        </header>

        {empty ? (
          <div className="flex flex-1 flex-col items-center justify-center px-4 pb-24">
            <div className="w-full max-w-2xl">
              <div className="mb-8 flex flex-col items-center gap-4 text-center">
                <Logo className="size-12" />
                <h1 className="font-serif text-4xl">{greeting(user?.email)}</h1>
                <p className="text-muted">Par quoi on commence ?</p>
              </div>
              {visibleError && (
                <p role="alert" className="mb-3 text-center text-sm text-danger">
                  {visibleError}
                </p>
              )}
              {composer}
            </div>
          </div>
        ) : (
          <>
            <div
              ref={scroller}
              className="flex-1 overflow-y-auto"
              onScroll={(event) => {
                const element = event.currentTarget
                pinned.current =
                  element.scrollHeight - element.scrollTop - element.clientHeight < 80
              }}
            >
              <MessageList
                messages={messages}
                pendingQuestion={here ? stream.question : null}
                streamingText={here ? stream.text : null}
                error={visibleError}
                onRegenerate={
                  id && selection && stream === null ? () => void regenerate(id, selection) : undefined
                }
              />
            </div>
            <div className="mx-auto w-full max-w-3xl px-4 pb-4">{composer}</div>
          </>
        )}
      </main>
      <ArtifactPanel />
      <SettingsDialog />
    </div>
  )
}
