import { useCallback, useEffect, useRef, useState } from 'react'

import * as api from '../lib/api'
import type { LibraryTrack, Song } from '../lib/api'

interface Props {
  onImported: (song: Song) => void
}

/**
 * Finding a song that is already on the server.
 *
 * Search rather than a folder tree. The library this reads is twelve thousand
 * files in four hundred folders, organised by artist and album, and clicking
 * down through that to reach one track is not a way to find anything — it is a
 * way to remember where you filed it, which is a different and harder task.
 *
 * Results stay on screen after being queued, marked as taken, because importing
 * three songs off one album is the normal case and a list that empties itself
 * loses your place.
 */
export function LibraryBrowser({ onImported }: Props) {
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [indexed, setIndexed] = useState(0)
  const [query, setQuery] = useState('')
  const [tracks, setTracks] = useState<LibraryTrack[]>([])
  const [searching, setSearching] = useState(false)
  const [imported, setImported] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const requestRef = useRef(0)

  const run = useCallback(async (term: string) => {
    const ticket = ++requestRef.current
    if (!term.trim()) {
      setTracks([])
      return
    }
    setSearching(true)
    try {
      const response = await api.searchLibrary(term)
      // A slower earlier request must not overwrite a faster later one.
      if (ticket !== requestRef.current) return
      setEnabled(response.enabled)
      setIndexed(response.indexed)
      setTracks(response.tracks)
      setError(null)
    } catch (failure) {
      if (ticket !== requestRef.current) return
      setError(failure instanceof Error ? failure.message : 'A busca falhou')
    } finally {
      if (ticket === requestRef.current) setSearching(false)
    }
  }, [])

  // First call also tells us whether a library is mounted at all.
  useEffect(() => {
    api
      .searchLibrary('')
      .then((response) => {
        setEnabled(response.enabled)
        setIndexed(response.indexed)
      })
      .catch(() => setEnabled(false))
  }, [])

  // Typing is throttled rather than sent per keystroke: the first search of a
  // session builds the index, and firing that off eight times while somebody
  // types a name would be eight walks of the whole tree.
  useEffect(() => {
    const timer = window.setTimeout(() => void run(query), 280)
    return () => window.clearTimeout(timer)
  }, [query, run])

  const bring = async (track: LibraryTrack) => {
    setBusy(track.path)
    try {
      onImported(await api.importFromLibrary(track.path, track.artist))
      setImported((previous) => new Set(previous).add(track.path))
      setError(null)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Falhou ao importar')
    } finally {
      setBusy(null)
    }
  }

  if (enabled === false) return null

  return (
    <section className="rounded-xl border border-slate-200 bg-panel dark:border-slate-800">
      <div className="border-b border-slate-100 p-4 dark:border-slate-800">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold tracking-tight">Música no servidor</h2>
          <span className="shrink-0 text-[11px] text-slate-400">
            {indexed.toLocaleString('pt-BR')} faixas
          </span>
        </div>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Buscar por artista, álbum ou título…"
          className="mt-3 w-full rounded-lg border border-slate-200 bg-canvas px-3.5 py-2.5 text-sm placeholder:text-slate-400 focus:border-accent focus:outline-none dark:border-slate-800"
        />
      </div>

      {error && <p className="px-4 pt-3 text-xs text-rose-500">{error}</p>}

      {query.trim() && !searching && !tracks.length && !error && (
        <p className="px-4 py-6 text-center text-xs text-slate-400">Nada com esse nome.</p>
      )}

      {!query.trim() && (
        <p className="px-4 py-6 text-center text-xs text-slate-400">
          Digite parte do artista ou do título. Acentos são opcionais.
        </p>
      )}

      <ul className="max-h-96 divide-y divide-slate-100 overflow-y-auto dark:divide-slate-800">
        {tracks.map((track) => (
          <li key={track.path} className="flex items-center gap-3 px-4 py-2.5">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm">{track.name}</p>
              <p className="truncate text-xs text-slate-500">
                {[track.artist, track.album].filter(Boolean).join(' · ') || '—'}
              </p>
            </div>
            <span className="shrink-0 text-[11px] tabular-nums text-slate-400">
              {Math.round(track.bytes / 1024 / 1024)} MB
            </span>
            <button
              type="button"
              onClick={() => void bring(track)}
              disabled={busy === track.path || imported.has(track.path)}
              className="shrink-0 rounded-full border border-slate-300 px-3 py-1 text-xs font-medium transition hover:border-accent hover:text-accent disabled:opacity-40 dark:border-slate-700"
            >
              {imported.has(track.path) ? 'na fila' : busy === track.path ? '…' : 'importar'}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
