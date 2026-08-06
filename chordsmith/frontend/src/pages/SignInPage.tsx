import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import * as api from '../lib/api'

/**
 * Sign in, or make the first account.
 *
 * The form defaults to creating an account when the server reports it has none,
 * because the very first person to open this app cannot sign in to anything and
 * being shown a login form is a dead end.
 */
export function SignInPage({ onSignedIn }: { onSignedIn: () => void }) {
  const navigate = useNavigate()
  const [mode, setMode] = useState<'login' | 'register' | null>(null)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Resolved once, from the server, so the first run offers registration.
  const [hasUsers, setHasUsers] = useState<boolean | null>(null)
  if (hasUsers === null) {
    void api
      .getAuthState()
      .then((state) => {
        setHasUsers(state.hasUsers)
        setMode(state.hasUsers ? 'login' : 'register')
      })
      .catch(() => {
        setHasUsers(true)
        setMode('login')
      })
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (mode === 'register') await api.register(username, password)
      else await api.login(username, password)
      onSignedIn()
      navigate('/')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Não consegui entrar')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-sm flex-col justify-center px-4">
      <h1 className="text-[26px] font-semibold tracking-tight">
        {mode === 'register' ? 'Criar conta' : 'Entrar'}
      </h1>
      <p className="mb-6 mt-1 text-sm text-slate-500">
        {mode === 'register'
          ? 'Esta é a primeira conta deste servidor.'
          : 'Entre para ver sua biblioteca e suas setlists.'}
      </p>

      <form onSubmit={submit} className="space-y-3">
        <input
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          placeholder="usuário"
          autoComplete="username"
          className="w-full rounded-lg border border-slate-200 bg-panel px-3.5 py-2.5 text-sm focus:border-accent focus:outline-none dark:border-slate-800"
        />
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="senha"
          autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
          className="w-full rounded-lg border border-slate-200 bg-panel px-3.5 py-2.5 text-sm focus:border-accent focus:outline-none dark:border-slate-800"
        />

        {error && <p className="text-sm text-rose-500">{error}</p>}

        <button
          type="submit"
          disabled={busy || username.length < 3 || password.length < 8}
          className="w-full rounded-lg bg-slate-900 py-2.5 text-sm font-semibold text-white disabled:opacity-40 dark:bg-white dark:text-slate-900"
        >
          {busy ? '…' : mode === 'register' ? 'Criar conta' : 'Entrar'}
        </button>
      </form>

      {hasUsers && (
        <button
          type="button"
          onClick={() => setMode(mode === 'register' ? 'login' : 'register')}
          className="mt-4 text-xs text-slate-500 hover:text-accent"
        >
          {mode === 'register' ? 'Já tenho conta' : 'Criar outra conta'}
        </button>
      )}

      <p className="mt-6 text-[11px] text-slate-400">
        A senha é guardada com PBKDF2 e sal próprio. Ninguém, nem o servidor, consegue lê-la de
        volta.
      </p>
    </div>
  )
}
