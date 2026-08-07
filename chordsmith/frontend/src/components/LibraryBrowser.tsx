import { useCallback, useEffect, useRef, useState } from 'react'

import * as api from '../lib/api'
import type { LibraryTrack, Mp3pmTrack, Song } from '../lib/api'
import { formatTime } from './Transport'

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

  // mp3.pm fallback, offered exactly when the server library comes back empty.
  const [webResults, setWebResults] = useState<Mp3pmTrack[]>([])
  const [webSearching, setWebSearching] = useState(false)
  const [webSearched, setWebSearched] = useState(false)
  const [webBusy, setWebBusy] = useState<string | null>(null)
  const [webImported, setWebImported] = useState<Set<string>>(new Set())
  const [webError, setWebError] = useState<string | null>(null)
  // One shared player for the whole result list, so previewing a track cannot
  // leave half a dozen streams playing at once.
  const [preview, setPreview] = useState<string | null>(null)
  const [hideOffStage, setHideOffStage] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)

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

  // A new query invalidates whatever the previous one found on mp3.pm.
  useEffect(() => {
    setWebResults([])
    setWebSearched(false)
    setWebError(null)
    setPreview(null)
    if (audioRef.current) audioRef.current.removeAttribute('src')
  }, [query])

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

  const searchWeb = async () => {
    if (!query.trim()) return
    setWebSearching(true)
    setWebError(null)
    try {
      const { results } = await api.searchMp3pm(query)
      setWebResults(results)
    } catch (failure) {
      setWebError(failure instanceof Error ? failure.message : 'A busca no mp3.pm falhou')
    } finally {
      setWebSearching(false)
      setWebSearched(true)
    }
  }

  const bringWeb = async (track: Mp3pmTrack) => {
    setWebBusy(track.soundId)
    try {
      onImported(await api.importMp3pm(query, track.soundId, track.title, track.artist))
      setWebImported((previous) => new Set(previous).add(track.soundId))
      setWebError(null)
    } catch (failure) {
      setWebError(failure instanceof Error ? failure.message : 'Falhou ao baixar do mp3.pm')
    } finally {
      setWebBusy(null)
    }
  }

  const togglePreview = (track: Mp3pmTrack) => {
    if (!audioRef.current) return
    if (preview === track.soundId) {
      audioRef.current.pause()
      audioRef.current.removeAttribute('src')
      setPreview(null)
    } else {
      audioRef.current.src = track.listenUrl
      setPreview(track.soundId)
      void audioRef.current.play().catch(() => setPreview(null))
    }
  }

  // A page of fifty results is mostly the same song several times over — a
  // live take, a radio edit, a karaoke mix. The off-stage versions are still
  // listed, but hidden by default so the studio recording reads first.
  const OFF_STAGE = /\b(live|ao vivo|remix|karaoke|karaokê|instrumental|acoustic|acústico|edit|extended|mashup|sped up|slowed|speed up)\b/i
  const visibleWeb = hideOffStage
    ? webResults.filter((track) => !OFF_STAGE.test(`${track.artist} ${track.title}`))
    : webResults

  if (enabled === false) return null

  return (
    <section className="rounded-xl border border-line bg-panel ">
      <div className="border-b border-line p-4 ">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold tracking-tight">Música no servidor</h2>
          <span className="shrink-0 text-[11px] text-ink-faint">
            {indexed.toLocaleString('pt-BR')} faixas
          </span>
        </div>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Buscar por artista, álbum ou título…"
          className="mt-3 w-full rounded-lg border border-line bg-canvas px-3.5 py-2.5 text-sm placeholder:text-ink-faint focus:border-accent focus:outline-none "
        />
      </div>

      {error && <p className="px-4 pt-3 text-xs text-rose-500">{error}</p>}

      {query.trim() && !searching && !tracks.length && !error && (
        <div className="px-4 py-6 text-center">
          <p className="text-xs text-ink-faint">Nada com esse nome no servidor.</p>
          <button
            type="button"
            onClick={() => void searchWeb()}
            disabled={webSearching}
            className="mt-3 rounded-full border border-accent px-4 py-1.5 text-xs font-medium text-accent transition hover:bg-accent-soft disabled:opacity-40 "
          >
            {webSearching
              ? 'Procurando no mp3.pm…'
              : webSearched
                ? 'Refazer busca no mp3.pm'
                : 'Buscar no mp3.pm e baixar'}
          </button>
        </div>
      )}

      {webError && <p className="px-4 pt-3 text-xs text-rose-500">{webError}</p>}

      {webSearched && !webSearching && !webError && webResults.length === 0 && (
        <p className="px-4 pb-4 text-center text-xs text-ink-faint">
          O mp3.pm também não achou nada para essa busca.
        </p>
      )}

      {hideOffStage && webResults.length > 0 && visibleWeb.length === 0 && (
        <p className="px-4 pb-4 text-center text-xs text-ink-faint">
          Só vieram versões ao vivo ou remixes — desmarque o filtro para vê-las.
        </p>
      )}

      {!query.trim() && (
        <p className="px-4 py-6 text-center text-xs text-ink-faint">
          Digite parte do artista ou do título. Acentos são opcionais.
        </p>
      )}

      <ul className="max-h-96 divide-y divide-[var(--color-line)] overflow-y-auto ">
        {tracks.map((track) => (
          <li key={track.path} className="flex items-center gap-3 px-4 py-2.5">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm">{track.name}</p>
              <p className="truncate text-xs text-ink-soft">
                {[track.artist, track.album].filter(Boolean).join(' · ') || '—'}
              </p>
            </div>
            <span className="shrink-0 text-[11px] tabular-nums text-ink-faint">
              {Math.round(track.bytes / 1024 / 1024)} MB
            </span>
            <button
              type="button"
              onClick={() => void bring(track)}
              disabled={busy === track.path || imported.has(track.path)}
              className="shrink-0 rounded-full border border-line px-3 py-1 text-xs font-medium transition hover:border-accent hover:text-accent disabled:opacity-40 "
            >
              {imported.has(track.path) ? 'na fila' : busy === track.path ? '…' : 'importar'}
            </button>
          </li>
        ))}
      </ul>

      {webResults.length > 0 && (
        <>
          <div className="flex items-center justify-between gap-2 border-t border-line px-4 py-2 text-[11px] text-ink-faint">
            <span>
              mp3.pm — baixar e analisar como no servidor · {visibleWeb.length}{' '}
              {visibleWeb.length === 1 ? 'faixa' : 'faixas'}
            </span>
            <label className="flex shrink-0 cursor-pointer items-center gap-1.5">
              <input
                type="checkbox"
                checked={hideOffStage}
                onChange={(event) => setHideOffStage(event.target.checked)}
                className="accent-[var(--color-accent)]"
              />
              esconder ao vivo e remixes
            </label>
          </div>
          <ul className="max-h-96 divide-y divide-[var(--color-line)] overflow-y-auto ">
            {visibleWeb.map((track) => (
              <li key={track.soundId} className="flex items-center gap-3 px-4 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">{track.title}</p>
                  <p className="truncate text-xs text-ink-soft">
                    {track.artist || '—'}
                    {track.duration > 0 ? ` · ${formatTime(track.duration)}` : ''}
                  </p>
                </div>
                {track.listenUrl ? (
                  <button
                    type="button"
                    onClick={() => togglePreview(track)}
                    aria-pressed={preview === track.soundId}
                    className="shrink-0 rounded-full border border-line px-3 py-1 text-xs font-medium transition hover:border-accent hover:text-accent "
                  >
                    {preview === track.soundId ? 'parar' : 'ouvir'}
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => void bringWeb(track)}
                  disabled={webBusy === track.soundId || webImported.has(track.soundId)}
                  className="shrink-0 rounded-full border border-accent px-3 py-1 text-xs font-medium text-accent transition hover:bg-accent-soft disabled:opacity-40 "
                >
                  {webImported.has(track.soundId)
                    ? 'na fila'
                    : webBusy === track.soundId
                      ? '…'
                      : 'baixar'}
                </button>
              </li>
            ))}
          </ul>
          <audio
            ref={audioRef}
            preload="none"
            onEnded={() => setPreview(null)}
            onError={() => setPreview(null)}
            className="hidden"
          />
        </>
      )}
    </section>
  )
}
