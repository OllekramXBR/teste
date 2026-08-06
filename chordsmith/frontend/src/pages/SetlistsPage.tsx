import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import * as api from '../lib/api'
import { Page, PageHeader } from '../components/Page'
import type { Setlist, SetlistSummary, Song } from '../lib/api'

/**
 * Setlists: what gets played, in what order.
 *
 * Reordering is buttons, not drag and drop. The device this is used on is a
 * tablet, often held, sometimes with a guitar in the way — and a drag that
 * misses turns into a scroll, which on a list you are trying to reorder is
 * indistinguishable from the app ignoring you. Two arrows always do exactly
 * what they say.
 */
export function SetlistsPage() {
  const [setlists, setSetlists] = useState<SetlistSummary[] | null>(null)
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setSetlists((await api.listSetlists()).setlists)
      setError(null)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Não consegui ler as setlists')
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const create = async () => {
    if (!name.trim()) return
    await api.createSetlist(name.trim())
    setName('')
    void refresh()
  }

  return (
    <Page>
      <PageHeader
        title="Setlists"
        description="A ordem do show. No modo palco, a próxima música já vem carregada."
      />

      <div className="flex gap-2">
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          onKeyDown={(event) => event.key === 'Enter' && void create()}
          placeholder="Nome do show"
          className="flex-1 rounded-lg border border-slate-200 bg-panel px-3.5 py-2.5 text-sm focus:border-accent focus:outline-none dark:border-slate-800"
        />
        <button
          type="button"
          onClick={() => void create()}
          disabled={!name.trim()}
          className="rounded-lg bg-slate-900 px-5 text-sm font-semibold text-white disabled:opacity-40 dark:bg-white dark:text-slate-900"
        >
          Criar
        </button>
      </div>

      {error && <p className="text-sm text-rose-500">{error}</p>}

      {setlists === null ? (
        <p className="text-center text-sm text-slate-500">Carregando…</p>
      ) : !setlists.length ? (
        <p className="py-10 text-center text-sm text-slate-500">
          Nenhuma setlist ainda. Crie uma acima.
        </p>
      ) : (
        <ul className="divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
          {setlists.map((setlist) => (
            <li key={setlist.id}>
              <Link
                to={`/setlists/${setlist.id}`}
                className="flex items-center justify-between gap-4 bg-panel p-4 transition-colors hover:bg-accent-soft"
              >
                <span className="truncate font-medium tracking-tight">{setlist.name}</span>
                <span className="shrink-0 text-xs text-slate-500">
                  {setlist.songCount} {setlist.songCount === 1 ? 'música' : 'músicas'}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Page>
  )
}

export function SetlistPage() {
  const { setlistId = '' } = useParams()
  const [setlist, setSetlist] = useState<Setlist | null>(null)
  const [library, setLibrary] = useState<Song[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [fetched, songs] = await Promise.all([api.getSetlist(setlistId), api.listSongs()])
      setSetlist(fetched)
      setLibrary(songs.songs)
      setError(null)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Não consegui abrir a setlist')
    }
  }, [setlistId])

  useEffect(() => {
    void load()
  }, [load])

  const save = async (ids: string[]) => {
    setSetlist(await api.setSetlistSongs(setlistId, ids))
  }

  if (error) return <p className="p-10 text-center text-sm text-rose-500">{error}</p>
  if (!setlist) return <p className="p-10 text-center text-sm text-slate-500">Carregando…</p>

  const ids = setlist.songs.map((song) => song.id)
  const available = library.filter((song) => !ids.includes(song.id) && song.status === 'ready')

  const move = (index: number, delta: number) => {
    const next = [...ids]
    const target = index + delta
    if (target < 0 || target >= next.length) return
    ;[next[index], next[target]] = [next[target], next[index]]
    void save(next)
  }

  const first = setlist.songs[0]

  return (
    <Page>
      <div>
        <Link to="/setlists" className="text-xs text-slate-500 hover:text-accent">
          ← Setlists
        </Link>
        <div className="mt-2">
          <PageHeader
            title={setlist.name}
            actions={
              first && (
                <Link
                  to={`/song/${first.id}/perform?setlist=${setlist.id}`}
                  className="rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white dark:bg-white dark:text-slate-900"
                >
                  Começar o show
                </Link>
              )
            }
          />
        </div>
      </div>

      {!setlist.songs.length ? (
        <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500 dark:border-slate-700">
          Setlist vazia. Adicione músicas abaixo.
        </p>
      ) : (
        <ol className="divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
          {setlist.songs.map((song, index) => (
            <li key={song.id} className="flex items-center gap-3 bg-panel p-3">
              <span className="w-6 shrink-0 text-center text-sm tabular-nums text-slate-400">
                {index + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{song.title}</p>
                <p className="truncate text-xs text-slate-500">
                  {song.keyName ?? '—'}
                  {song.bpm ? ` · ${Math.round(song.bpm)} BPM` : ''}
                  {song.lyricsStatus === 'ready' ? ' · letra' : ''}
                  {song.stemsStatus === 'ready' ? ' · pistas' : ''}
                </p>
              </div>
              <div className="flex shrink-0 gap-1">
                <Arrow label="Subir" onClick={() => move(index, -1)} disabled={index === 0}>
                  ↑
                </Arrow>
                <Arrow
                  label="Descer"
                  onClick={() => move(index, 1)}
                  disabled={index === setlist.songs.length - 1}
                >
                  ↓
                </Arrow>
                <Arrow
                  label="Tirar da setlist"
                  onClick={() => void save(ids.filter((id) => id !== song.id))}
                >
                  ✕
                </Arrow>
              </div>
            </li>
          ))}
        </ol>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold tracking-tight">Adicionar da biblioteca</h2>
        {!available.length ? (
          <p className="text-xs text-slate-500">Todas as músicas analisadas já estão na setlist.</p>
        ) : (
          <ul className="divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
            {available.map((song) => (
              <li key={song.id} className="flex items-center gap-3 bg-panel p-3">
                <span className="min-w-0 flex-1 truncate text-sm">{song.title}</span>
                <button
                  type="button"
                  onClick={() => void save([...ids, song.id])}
                  className="shrink-0 rounded-full border border-slate-300 px-3 py-1 text-xs font-medium hover:border-accent hover:text-accent dark:border-slate-700"
                >
                  adicionar
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </Page>
  )
}

function Arrow({
  children,
  label,
  onClick,
  disabled,
}: {
  children: React.ReactNode
  label: string
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className="h-10 w-10 rounded-lg border border-slate-300 text-sm text-slate-500 transition hover:border-accent hover:text-accent disabled:opacity-30 dark:border-slate-700"
    >
      {children}
    </button>
  )
}
