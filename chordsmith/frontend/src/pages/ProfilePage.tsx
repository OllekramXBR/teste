import { useEffect, useState } from 'react'

import * as api from '../lib/api'
import type { AuthUser } from '../lib/api'

/**
 * The account: display name, password, and who else is on this server.
 *
 * The list of people is here rather than hidden in an admin screen because a
 * shared library only makes sense if you can see who you are sharing it with.
 */
export function ProfilePage({ user, onChanged }: { user: AuthUser | null; onChanged: () => void }) {
  const [displayName, setDisplayName] = useState(user?.displayName ?? '')
  const [current, setCurrent] = useState('')
  const [replacement, setReplacement] = useState('')
  const [people, setPeople] = useState<AuthUser[]>([])
  const [message, setMessage] = useState<{ tone: 'ok' | 'bad'; text: string } | null>(null)

  useEffect(() => {
    api
      .listUsers()
      .then(({ users }) => setPeople(users))
      .catch(() => setPeople([]))
  }, [])

  if (!user) {
    return (
      <p className="p-16 text-center text-sm text-slate-500">
        Entre para ver seu perfil. As contas estão criadas, mas o servidor ainda não exige login.
      </p>
    )
  }

  const saveName = async () => {
    try {
      await api.updateProfile(displayName)
      onChanged()
      setMessage({ tone: 'ok', text: 'Nome salvo.' })
    } catch (error) {
      setMessage({ tone: 'bad', text: error instanceof Error ? error.message : 'Não salvou' })
    }
  }

  const savePassword = async () => {
    try {
      await api.changePassword(current, replacement)
      setCurrent('')
      setReplacement('')
      onChanged()
      setMessage({
        tone: 'ok',
        text: 'Senha trocada. Todas as sessões foram encerradas — entre de novo.',
      })
    } catch (error) {
      setMessage({ tone: 'bad', text: error instanceof Error ? error.message : 'Não trocou' })
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-8 px-4 py-8">
      <header>
        <h1 className="text-[26px] font-semibold tracking-tight">Perfil</h1>
        <p className="mt-1 text-sm text-slate-500">
          Entrou como <span className="font-medium">{user.username}</span>.
        </p>
      </header>

      {message && (
        <p className={message.tone === 'ok' ? 'text-sm text-emerald-600' : 'text-sm text-rose-500'}>
          {message.text}
        </p>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-semibold tracking-tight">Nome de exibição</h2>
        <div className="flex gap-2">
          <input
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            placeholder={user.username}
            className="flex-1 rounded-lg border border-slate-200 bg-panel px-3.5 py-2.5 text-sm focus:border-accent focus:outline-none dark:border-slate-800"
          />
          <button
            type="button"
            onClick={() => void saveName()}
            className="rounded-lg border border-slate-300 px-4 text-sm font-medium dark:border-slate-700"
          >
            Salvar
          </button>
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold tracking-tight">Trocar senha</h2>
        <input
          type="password"
          value={current}
          onChange={(event) => setCurrent(event.target.value)}
          placeholder="senha atual"
          autoComplete="current-password"
          className="w-full rounded-lg border border-slate-200 bg-panel px-3.5 py-2.5 text-sm focus:border-accent focus:outline-none dark:border-slate-800"
        />
        <input
          type="password"
          value={replacement}
          onChange={(event) => setReplacement(event.target.value)}
          placeholder="senha nova (mínimo 8)"
          autoComplete="new-password"
          className="w-full rounded-lg border border-slate-200 bg-panel px-3.5 py-2.5 text-sm focus:border-accent focus:outline-none dark:border-slate-800"
        />
        <button
          type="button"
          onClick={() => void savePassword()}
          disabled={!current || replacement.length < 8}
          className="w-full rounded-lg bg-slate-900 py-2.5 text-sm font-semibold text-white disabled:opacity-40 dark:bg-white dark:text-slate-900"
        >
          Trocar senha
        </button>
        <p className="text-[11px] text-slate-400">
          Trocar a senha encerra todas as sessões, inclusive esta. É de propósito: se você está
          trocando porque alguém entrou, deixar a sessão dele viva não adiantaria nada.
        </p>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold tracking-tight">Quem mais usa este servidor</h2>
        <ul className="divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
          {people.map((person) => (
            <li key={person.id} className="flex items-center justify-between bg-panel px-4 py-2.5">
              <span className="text-sm">{person.displayName || person.username}</span>
              {person.id === user.id && <span className="text-xs text-slate-400">você</span>}
            </li>
          ))}
          {!people.length && (
            <li className="bg-panel px-4 py-3 text-xs text-slate-400">Só você, por enquanto.</li>
          )}
        </ul>
        <p className="mt-2 text-[11px] text-slate-400">
          As músicas são compartilhadas entre todos por padrão; as setlists não. Cada música pode
          ser tornada privada na página dela.
        </p>
      </section>
    </div>
  )
}
