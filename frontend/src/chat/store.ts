import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Selection } from '../api/types'

export interface StreamState {
  /** null tant que le serveur n'a pas créé la conversation. */
  conversationId: string | null
  /** Question affichée en attendant que le serveur l'ait enregistrée. */
  question: string | null
  text: string
}

interface ChatState {
  selection: Selection | null
  stream: StreamState | null
  error: { conversationId: string | null; message: string } | null
  sidebarOpen: boolean
  settingsOpen: boolean
  setSelection: (selection: Selection) => void
  toggleSidebar: () => void
  setSettingsOpen: (open: boolean) => void
}

export const useChat = create<ChatState>()(
  persist(
    (set) => ({
      selection: null,
      stream: null,
      error: null,
      sidebarOpen: true,
      settingsOpen: false,
      setSelection: (selection) => set({ selection }),
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      setSettingsOpen: (settingsOpen) => set({ settingsOpen }),
    }),
    {
      name: 'llmchat',
      partialize: (state) => ({ selection: state.selection, sidebarOpen: state.sidebarOpen }),
    },
  ),
)
