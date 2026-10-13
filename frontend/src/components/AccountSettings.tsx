import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { queryClient, useChangePassword, useDeleteAccount, useMe } from '../api/hooks'
import { useChat } from '../chat/store'

const MIN_PASSWORD = 8

const field =
  'w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent'

function PasswordForm() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const change = useChangePassword()
  const tooShort = next.length > 0 && next.length < MIN_PASSWORD

  function submit(event: FormEvent) {
    event.preventDefault()
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          setCurrent('')
          setNext('')
        },
      },
    )
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 rounded-2xl border border-border p-4">
      <h3 className="font-medium">Changer de mot de passe</h3>
      <label className="flex flex-col gap-1.5 text-sm">
        Mot de passe actuel
        <input
          type="password"
          required
          autoComplete="current-password"
          value={current}
          onChange={(event) => setCurrent(event.target.value)}
          className={field}
        />
      </label>
      <label className="flex flex-col gap-1.5 text-sm">
        Nouveau mot de passe
        <input
          type="password"
          required
          autoComplete="new-password"
          value={next}
          onChange={(event) => setNext(event.target.value)}
          className={field}
        />
        <span className={`text-xs ${tooShort ? 'text-danger' : 'text-muted'}`}>
          {MIN_PASSWORD} caractères minimum
        </span>
      </label>
      {change.isError && (
        <p role="alert" className="text-sm text-danger">
          {change.error.message}
        </p>
      )}
      {change.isSuccess && (
        <p role="status" className="text-sm text-success">
          Mot de passe modifié. Vos autres appareils ont été déconnectés.
        </p>
      )}
      <button
        type="submit"
        disabled={!current || next.length < MIN_PASSWORD || change.isPending}
        className="self-start rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-40"
      >
        Modifier le mot de passe
      </button>
    </form>
  )
}

function DeleteAccount() {
  const [confirming, setConfirming] = useState(false)
  const [password, setPassword] = useState('')
  const remove = useDeleteAccount()
  const setSettingsOpen = useChat((state) => state.setSettingsOpen)
  const navigate = useNavigate()

  function submit(event: FormEvent) {
    event.preventDefault()
    remove.mutate(password, {
      onSuccess: () => {
        setSettingsOpen(false)
        queryClient.clear()
        navigate('/login')
      },
    })
  }

  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-danger/40 p-4">
      <h3 className="font-medium">Supprimer mon compte</h3>
      <p className="text-sm text-muted">
        Le compte, les clés API enregistrées et toutes les conversations sont effacés
        définitivement. Cette action ne peut pas être annulée.
      </p>
      {confirming ? (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1.5 text-sm">
            Mot de passe, pour confirmer
            <input
              type="password"
              required
              autoFocus
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className={field}
            />
          </label>
          {remove.isError && (
            <p role="alert" className="text-sm text-danger">
              {remove.error.message}
            </p>
          )}
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={!password || remove.isPending}
              className="rounded-lg bg-danger px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-40"
            >
              Supprimer définitivement
            </button>
            <button
              type="button"
              className="text-sm text-muted hover:underline"
              onClick={() => {
                setConfirming(false)
                setPassword('')
                remove.reset()
              }}
            >
              Annuler
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className="self-start rounded-lg border border-danger/50 px-3 py-2 text-sm font-medium text-danger hover:bg-danger/5"
        >
          Supprimer mon compte…
        </button>
      )}
    </section>
  )
}

export function AccountSettings() {
  const { data: user } = useMe()
  return (
    <>
      <p className="text-sm text-muted">
        Connecté en tant que <span className="font-medium text-text">{user?.email}</span>
      </p>
      <PasswordForm />
      <DeleteAccount />
    </>
  )
}
