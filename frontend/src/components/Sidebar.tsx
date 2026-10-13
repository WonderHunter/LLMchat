import { LogOut, Moon, PanelLeftClose, Pencil, Settings, SquarePen, Sun, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { NavLink, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import {
  queryClient,
  useConversations,
  useDeleteConversation,
  useMe,
  useRenameConversation,
} from '../api/hooks'
import type { Conversation } from '../api/types'
import { isDark, useChat } from '../chat/store'
import { Logo } from './Logo'

const DAY = 86_400_000

function periodOf(iso: string): string {
  const today = new Date().setHours(0, 0, 0, 0)
  const days = Math.round((today - new Date(iso).setHours(0, 0, 0, 0)) / DAY)
  if (days <= 0) return "Aujourd'hui"
  if (days === 1) return 'Hier'
  if (days < 7) return '7 derniers jours'
  if (days < 30) return '30 derniers jours'
  return 'Plus ancien'
}

function groupByPeriod(conversations: Conversation[]): [string, Conversation[]][] {
  const groups = new Map<string, Conversation[]>()
  for (const conversation of conversations) {
    const period = periodOf(conversation.updated_at)
    groups.set(period, [...(groups.get(period) ?? []), conversation])
  }
  return [...groups]
}

const iconButton =
  'rounded-md p-1.5 text-muted transition-colors hover:bg-border hover:text-text'

function ConversationItem({ conversation }: { conversation: Conversation }) {
  const [mode, setMode] = useState<'idle' | 'renaming' | 'deleting'>('idle')
  const [title, setTitle] = useState(conversation.title)
  const rename = useRenameConversation()
  const remove = useDeleteConversation()
  const navigate = useNavigate()
  const { id: openId } = useParams()

  function submitRename(event: FormEvent) {
    event.preventDefault()
    const next = title.trim()
    if (next && next !== conversation.title) rename.mutate({ id: conversation.id, title: next })
    setMode('idle')
  }

  if (mode === 'renaming') {
    return (
      <form onSubmit={submitRename} className="px-1">
        <input
          autoFocus
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          onBlur={submitRename}
          onKeyDown={(event) => event.key === 'Escape' && setMode('idle')}
          aria-label="Titre de la conversation"
          className="w-full rounded-lg border border-accent bg-surface px-2 py-1.5 text-sm outline-none"
        />
      </form>
    )
  }

  if (mode === 'deleting') {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-hover px-3 py-1.5 text-sm">
        <span className="flex-1 truncate">Supprimer ?</span>
        <button
          type="button"
          className="font-medium text-danger hover:underline"
          onClick={() =>
            remove.mutate(conversation.id, {
              onSuccess: () => openId === conversation.id && navigate('/'),
            })
          }
        >
          Oui
        </button>
        <button type="button" className="text-muted hover:underline" onClick={() => setMode('idle')}>
          Non
        </button>
      </div>
    )
  }

  return (
    <NavLink
      to={`/c/${conversation.id}`}
      className={({ isActive }) =>
        `group flex items-center rounded-lg pr-1 pl-3 text-sm hover:bg-hover ${isActive ? 'bg-hover font-medium' : ''}`
      }
    >
      <span className="flex-1 truncate py-2">{conversation.title}</span>
      <span className="hidden shrink-0 group-hover:flex group-focus-within:flex">
        <button
          type="button"
          title="Renommer"
          aria-label="Renommer"
          className={iconButton}
          onClick={(event) => {
            event.preventDefault()
            setTitle(conversation.title)
            setMode('renaming')
          }}
        >
          <Pencil className="size-3.5" />
        </button>
        <button
          type="button"
          title="Supprimer"
          aria-label="Supprimer"
          className={iconButton}
          onClick={(event) => {
            event.preventDefault()
            setMode('deleting')
          }}
        >
          <Trash2 className="size-3.5" />
        </button>
      </span>
    </NavLink>
  )
}

export function Sidebar() {
  const { data: conversations } = useConversations()
  const { data: user } = useMe()
  const toggleSidebar = useChat((state) => state.toggleSidebar)
  const setSettingsOpen = useChat((state) => state.setSettingsOpen)
  const theme = useChat((state) => state.theme)
  const setTheme = useChat((state) => state.setTheme)
  const dark = isDark(theme)
  const navigate = useNavigate()

  async function logout() {
    await api('/api/auth/logout', { method: 'POST' })
    queryClient.clear()
    navigate('/login')
  }

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-border bg-sidebar max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-30 max-md:shadow-2xl">
      <div className="flex items-center justify-between px-3 pt-3 pb-2">
        <NavLink to="/" className="flex items-center gap-2 px-1">
          <Logo />
          <span className="font-serif text-lg font-semibold">LLMchat</span>
        </NavLink>
        <button
          type="button"
          onClick={toggleSidebar}
          title="Masquer la barre latérale"
          aria-label="Masquer la barre latérale"
          className={iconButton}
        >
          <PanelLeftClose className="size-5" />
        </button>
      </div>

      <div className="px-2 pb-2">
        <NavLink
          to="/"
          className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium hover:bg-hover"
        >
          <SquarePen className="size-4 text-accent" />
          Nouvelle conversation
        </NavLink>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 pb-2" aria-label="Conversations">
        {conversations?.length === 0 && (
          <p className="px-3 py-2 text-sm text-muted">Aucune conversation pour l'instant.</p>
        )}
        {groupByPeriod(conversations ?? []).map(([period, items]) => (
          <section key={period} className="mb-3">
            <h2 className="px-3 pt-2 pb-1 text-xs font-semibold text-muted">{period}</h2>
            <div className="flex flex-col gap-0.5">
              {items.map((conversation) => (
                <ConversationItem key={conversation.id} conversation={conversation} />
              ))}
            </div>
          </section>
        ))}
      </nav>

      <div className="flex items-center gap-1 border-t border-border p-2">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-sm font-semibold text-accent uppercase">
          {user?.email[0]}
        </span>
        <span className="min-w-0 flex-1 truncate px-1 text-sm" title={user?.email}>
          {user?.email}
        </span>
        <button
          type="button"
          onClick={() => setTheme(dark ? 'light' : 'dark')}
          title={dark ? 'Thème clair' : 'Thème sombre'}
          aria-label={dark ? 'Thème clair' : 'Thème sombre'}
          className={iconButton}
        >
          {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </button>
        <button
          type="button"
          onClick={() => setSettingsOpen(true)}
          title="Réglages"
          aria-label="Réglages"
          className={iconButton}
        >
          <Settings className="size-4" />
        </button>
        <button
          type="button"
          onClick={() => void logout()}
          title="Se déconnecter"
          aria-label="Se déconnecter"
          className={iconButton}
        >
          <LogOut className="size-4" />
        </button>
      </div>
    </aside>
  )
}
