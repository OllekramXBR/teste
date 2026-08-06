import { useCallback, useEffect, useState } from 'react'

import * as api from '../lib/api'
import type { LibraryEntry, Song } from '../lib/api'

interface Props {
  artist: string
  onImported: (song: Song) => void
}

/**
 * Picking music that is already on the server.
 *
 * The alternative — dragging a file into the browser — sends bytes off the
 * array, across the network, and back to the machine they started on. For a
 * folder of albums on a NAS that is minutes of waiting for nothing.
 *
 * Importing several at once is the normal case, so files stay listed after they
 * are queued, marked as taken, rather than disappearing and making the user
 * lose their place in a long folder.
 */
export function LibraryBrowser({ artist, onImported }: Props) {
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [path, setPath] = useState('')
  const [parent, setParent] = useState<string | null>(null)
  const [entries, setEntries] = useState<LibraryEntry[]>([])
  const [imported, setImported] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (target: string) => {
    try {
      const response = await api.browseLibrary(target)
      setEnabled(response.enabled)
      setPath(response.path)
      setParent(response.parent)
      setEntries(response.entries)
      setError(null)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Não consegui ler essa pasta')
    }
  }, [])

  useEffect(() => {
    void load('')
  }, [load])

  const bring = async (entry: LibraryEntry) => {
    setBusy(entry.path)
    try {
      onImported(await api.importFromLibrary(entry.path, artist))
      setImported((previous) => new Set(previous).add(entry.path))
      setError(null)
    } catch (importError) {
      setError(importError instanceof Error ? importError.message : 'Falhou ao importar')
    } finally {
      setBusy(null)
    }
  }

  if (enabled === false) return null

  return (
    <section className="rounded-xl border border-slate-200 bg-panel dark:border-slate-800">
      <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3 dark:border-slate-800">
        <h2 className="text-sm font-semibold tracking-tight">Música no servidor</h2>
        <span className="truncate text-xs text-slate-400">/{path}</span>
      </div>

      {error && <p className="px-4 pt-3 text-xs text-rose-500">{error}</p>}

      <ul className="max-h-80 divide-y divide-slate-100 overflow-y-auto dark:divide-slate-800">
        {parent !== null && (
          <li>
            <button
              type="button"
              onClick={() => void load(parent)}
              className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm text-slate-500 hover:bg-accent-soft"
            >
              ← pasta acima
            </button>
          </li>
        )}
        {entries.map((entry) => (
          <li key={entry.path}>
            {entry.isDir ? (
              <button
                type="button"
                onClick={() => void load(entry.path)}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm hover:bg-accent-soft"
              >
                <span className="text-slate-400">📁</span>
                <span className="truncate">{entry.name}</span>
              </button>
            ) : (
              <div className="flex items-center gap-3 px-4 py-2.5 text-sm">
                <span className="min-w-0 flex-1 truncate">{entry.name}</span>
                <span className="shrink-0 text-[11px] tabular-nums text-slate-400">
                  {Math.round(entry.bytes / 1024 / 1024)} MB
                </span>
                <button
                  type="button"
                  onClick={() => void bring(entry)}
                  disabled={busy === entry.path || imported.has(entry.path)}
                  className="shrink-0 rounded-full border border-slate-300 px-3 py-1 text-xs font-medium transition hover:border-accent hover:text-accent disabled:opacity-40 dark:border-slate-700"
                >
                  {imported.has(entry.path)
                    ? 'na fila'
                    : busy === entry.path
                      ? '…'
                      : 'importar'}
                </button>
              </div>
            )}
          </li>
        ))}
        {!entries.length && parent === null && (
          <li className="px-4 py-6 text-center text-xs text-slate-400">
            Nada aqui. Monte uma pasta de música no servidor com LIBRARY_DIR.
          </li>
        )}
      </ul>
    </section>
  )
}
