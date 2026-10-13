import { QueryClient, useMutation, useQuery } from '@tanstack/react-query'
import { ApiError, api } from './client'
import type { Conversation, ConversationDetail, KeyStatus, ProviderModels, User } from './types'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: 30_000, refetchOnWindowFocus: false },
  },
})

export const keys = {
  me: ['me'] as const,
  providerKeys: ['keys'] as const,
  models: ['models'] as const,
  conversations: ['conversations'] as const,
  conversation: (id: string) => ['conversation', id] as const,
}

/** L'utilisateur connecté, ou null s'il n'y a pas de session. */
export function useMe() {
  return useQuery({
    queryKey: keys.me,
    staleTime: Infinity,
    queryFn: async () => {
      try {
        return await api<User>('/api/auth/me')
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null
        throw error
      }
    },
  })
}

export function useAuthConfig() {
  return useQuery({
    queryKey: ['auth-config'],
    staleTime: Infinity,
    queryFn: () => api<{ allow_registration: boolean; demo: boolean }>('/api/auth/config'),
  })
}

export function useProviderKeys() {
  return useQuery({
    queryKey: keys.providerKeys,
    queryFn: () => api<KeyStatus[]>('/api/keys'),
  })
}

export function useModels() {
  return useQuery({
    queryKey: keys.models,
    staleTime: 5 * 60_000,
    queryFn: () => api<ProviderModels[]>('/api/models'),
  })
}

export function useConversations() {
  return useQuery({
    queryKey: keys.conversations,
    queryFn: () => api<Conversation[]>('/api/conversations'),
  })
}

export function useConversation(id: string | undefined) {
  return useQuery({
    queryKey: keys.conversation(id ?? ''),
    enabled: Boolean(id),
    queryFn: () => api<ConversationDetail>(`/api/conversations/${id}`),
  })
}

function refreshKeysAndModels() {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: keys.providerKeys }),
    queryClient.invalidateQueries({ queryKey: keys.models }),
  ])
}

export function useSaveKey() {
  return useMutation({
    mutationFn: ({ provider, key }: { provider: string; key: string }) =>
      api<KeyStatus>(`/api/keys/${provider}`, { method: 'PUT', body: { key } }),
    onSuccess: refreshKeysAndModels,
  })
}

export function useDeleteKey() {
  return useMutation({
    mutationFn: (provider: string) => api<void>(`/api/keys/${provider}`, { method: 'DELETE' }),
    onSuccess: refreshKeysAndModels,
  })
}

export function useSetFreeOnly() {
  return useMutation({
    mutationFn: ({ provider, freeOnly }: { provider: string; freeOnly: boolean }) =>
      api<KeyStatus>(`/api/keys/${provider}`, { method: 'PATCH', body: { free_only: freeOnly } }),
    onSuccess: refreshKeysAndModels,
  })
}

export function useRenameConversation() {
  return useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      api<Conversation>(`/api/conversations/${id}`, { method: 'PATCH', body: { title } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.conversations }),
  })
}

export function useDeleteConversation() {
  return useMutation({
    mutationFn: (id: string) => api<void>(`/api/conversations/${id}`, { method: 'DELETE' }),
    onSuccess: (_data, id) => {
      queryClient.removeQueries({ queryKey: keys.conversation(id) })
      return queryClient.invalidateQueries({ queryKey: keys.conversations })
    },
  })
}
