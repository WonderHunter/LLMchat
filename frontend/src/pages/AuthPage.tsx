import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { keys, queryClient, useAuthConfig, useMe } from '../api/hooks'
import type { User } from '../api/types'
import { DemoBanner } from '../components/DemoBanner'
import { Logo } from '../components/Logo'

const MIN_PASSWORD = 8

const field =
  'w-full rounded-xl border border-border bg-bg px-4 py-2.5 outline-none focus:border-accent'

export function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const registering = mode === 'register'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()
  const { data: user } = useMe()
  const { data: config } = useAuthConfig()

  const submit = useMutation({
    mutationFn: () =>
      api<User>(`/api/auth/${mode}`, { method: 'POST', body: { email, password } }),
    onSuccess: (loggedIn) => {
      queryClient.clear()
      queryClient.setQueryData(keys.me, loggedIn)
      navigate('/')
    },
  })

  if (user) return <Navigate to="/" replace />

  const closed = registering && config?.allow_registration === false
  const tooShort = registering && password.length > 0 && password.length < MIN_PASSWORD

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!tooShort && !closed) submit.mutate()
  }

  return (
    <main className="flex min-h-full flex-col">
      <DemoBanner />
      <div className="m-auto w-full max-w-sm p-4">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <Logo className="size-16" />
          <h1 className="font-serif text-3xl">
            {registering ? 'Créer un compte' : 'Bon retour sur LLMchat'}
          </h1>
        </div>

        {closed ? (
          <p className="rounded-2xl border border-border bg-surface p-4 text-center text-sm text-muted">
            Les inscriptions sont fermées sur ce serveur.
          </p>
        ) : (
          <form
            onSubmit={onSubmit}
            className="flex flex-col gap-3 rounded-3xl border border-border bg-surface p-6 shadow-sm"
          >
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              E-mail
              <input
                type="email"
                required
                autoFocus
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className={field}
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              Mot de passe
              <input
                type="password"
                required
                autoComplete={registering ? 'new-password' : 'current-password'}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className={field}
              />
              {registering && (
                <span className={`text-xs font-normal ${tooShort ? 'text-danger' : 'text-muted'}`}>
                  {MIN_PASSWORD} caractères minimum
                </span>
              )}
            </label>
            {submit.isError && (
              <p role="alert" className="text-sm text-danger">
                {submit.error.message}
              </p>
            )}
            <button
              type="submit"
              disabled={submit.isPending || tooShort}
              className="mt-1 rounded-xl bg-accent py-2.5 font-medium text-white hover:bg-accent-hover disabled:opacity-50"
            >
              {registering ? 'Créer mon compte' : 'Se connecter'}
            </button>
          </form>
        )}

        <p className="mt-4 text-center text-sm text-muted">
          {registering ? 'Déjà un compte ? ' : 'Pas encore de compte ? '}
          <Link to={registering ? '/login' : '/register'} className="text-accent hover:underline">
            {registering ? 'Se connecter' : 'Créer un compte'}
          </Link>
        </p>
      </div>
    </main>
  )
}
