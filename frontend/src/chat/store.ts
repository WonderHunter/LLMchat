import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Attachment, Selection } from '../api/types'

export interface StreamState {
  /** null tant que le serveur n'a pas créé la conversation. */
  conversationId: string | null
  /** Question affichée en attendant que le serveur l'ait enregistrée. */
  question: string | null
  /** Pièces jointes de cette question, affichées avec elle. */
  attachments: Attachment[]
  text: string
}

export interface Artifact {
  language: string
  code: string
}

export type Theme = 'system' | 'light' | 'dark'

interface ChatState {
  selection: Selection | null
  stream: StreamState | null
  error: { conversationId: string | null; message: string } | null
  sidebarOpen: boolean
  settingsOpen: boolean
  artifact: Artifact | null
  theme: Theme
  setSelection: (selection: Selection) => void
  toggleSidebar: () => void
  setSettingsOpen: (open: boolean) => void
  setArtifact: (artifact: Artifact | null) => void
  setTheme: (theme: Theme) => void
}

export const useChat = create<ChatState>()(
  persist(
    (set) => ({
      selection: null,
      stream: null,
      error: null,
      sidebarOpen: true,
      settingsOpen: false,
      artifact: null,
      theme: 'system',
      setSelection: (selection) => set({ selection }),
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      setSettingsOpen: (settingsOpen) => set({ settingsOpen }),
      setArtifact: (artifact) => set({ artifact }),
      setTheme: (theme) => set({ theme }),
    }),
    {
      // Clé lue aussi par le script de index.html, qui applique le thème avant le premier rendu.
      name: 'llmchat',
      partialize: (state) => ({
        selection: state.selection,
        sidebarOpen: state.sidebarOpen,
        theme: state.theme,
      }),
    },
  ),
)

export function isDark(theme: Theme): boolean {
  return theme === 'dark' || (theme === 'system' && matchMedia('(prefers-color-scheme: dark)').matches)
}
