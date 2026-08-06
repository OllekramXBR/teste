import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import * as api from '../lib/api'
import type { Song } from '../lib/api'
import { formatTime } from '../components/Transport'

const POLL_INTERVAL_MS = 2000

function StatusBadge({ status }: { status: Song['status'] }) {
  const styles: Record<Song['status'], string> = {
    ready: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300',
    failed: 'bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300',
    analyzing: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300',
    pending: 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
  }
  const labels: Record<Song['status'], string> = {
    ready: 'pronta',
    failed: 'falhou',
    analyzing: 'analisando…',
    pending: 'na fila',
  }
  return (
    <span
      className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${styles[status]}`}
    >
      {labels[status]}
    </span>
  )
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="shrink-0 rounded-full border border-slate-200 px-1.5 py-0.5 text-[10px] text-slate-500 dark:border-slate-700">
      {children}
    </span>
  )
}

function Uploader({ onUploaded }: { onUploaded: (song: Song) => void }) {
  const [dragging, setDragging] = useState(false)
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [artist, setArtist] = useState('')
  const inputRef = useRef<HTMLInputElement | null>(null)

  const upload = useCallback(
    async (files: FileList | File[]) => {
      setError(null)
      for (const file of Array.from(files)) {
        try {
          setProgress(0)
          const song = await api.uploadSong(file, { artist }, setProgress)
          onUploaded(song)
        } catch (uploadError) {
          setError(uploadError instanceof Error ? uploadError.message : 'Upload failed')
        } finally {
          setProgress(null)
        }
      }
    },
    [artist, onUploaded],
  )

  return (
    <div className="space-y-3">
      <div
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          if (event.dataTransfer.files.length) void upload(event.dataTransfer.files)
        }}
        onClick={() => inputRef.current?.click()}
        className={`cursor-pointer rounded-2xl border border-dashed p-10 text-center transition-colors ${
          dragging
            ? 'border-accent bg-accent-soft'
            : 'border-slate-300 hover:border-accent dark:border-slate-700'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".mp3,.wav,.flac,.ogg,.oga,.aiff,.aif,.m4a,.aac,audio/*"
          multiple
          className="hidden"
          onChange={(event) => {
            if (event.target.files?.length) void upload(event.target.files)
            event.target.value = ''
          }}
        />
        <p className="text-[15px] font-semibold tracking-tight">
          Arraste um arquivo de áudio para tirar a cifra
        </p>
        <p className="mt-1.5 text-xs text-slate-500">
          MP3, WAV, FLAC, OGG, AIFF, M4A · analisado aqui no servidor, nada sai da sua rede
        </p>
        {progress !== null && (
          <div className="mx-auto mt-5 h-1 w-56 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
            <div
              className="h-full bg-accent transition-all"
              style={{ width: `${Math.round(progress * 100)}%` }}
            />
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <label htmlFor="artist" className="shrink-0 text-xs text-slate-500">
          Artista do próximo envio
        </label>
        <input
          id="artist"
          value={artist}
          onChange={(event) => setArtist(event.target.value)}
          placeholder="opcional"
          className="flex-1 rounded-lg border border-slate-200 bg-panel px-2.5 py-1.5 text-sm placeholder:text-slate-400 focus:border-accent focus:outline-none dark:border-slate-800"
        />
      </div>

      {error && <p className="text-sm text-rose-500">{error}</p>}
    </div>
  )
}

export function LibraryPage() {
  const [songs, setSongs] = useState<Song[] | null>(null)
  const [search, setSearch] = useState('')
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async (term: string) => {
    try {
      const { songs: fetched } = await api.listSongs(term)
      setSongs(fetched)
      setError(null)
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not reach the API')
    }
  }, [])

  useEffect(() => {
    void refresh(search)
  }, [refresh, search])

  // Keep polling while anything is still in the queue.
  useEffect(() => {
    if (!songs?.some((song) => song.status === 'pending' || song.status === 'analyzing')) return
    const timer = window.setTimeout(() => void refresh(search), POLL_INTERVAL_MS)
    return () => window.clearTimeout(timer)
  }, [songs, refresh, search])

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-8">
      <header className="text-center">
        <h1 className="text-[28px] font-semibold tracking-tight">Sua música, aberta</h1>
        <p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-slate-500">
          Suba um arquivo e o Metatron acha a batida, o tom e os acordes. Depois transcreve a
          letra e separa a voz principal da banda, para você cantar por cima da sua própria
          gravação.
        </p>
      </header>

      <Uploader onUploaded={(song) => setSongs((previous) => [song, ...(previous ?? [])])} />

      <input
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Buscar na biblioteca"
        className="w-full rounded-lg border border-slate-200 bg-panel px-3.5 py-2.5 text-sm transition-colors placeholder:text-slate-400 focus:border-accent focus:outline-none dark:border-slate-800"
      />

      {error && <p className="text-sm text-rose-500">{error}</p>}

      {songs === null ? (
        <p className="text-center text-sm text-slate-500">Carregando a biblioteca…</p>
      ) : songs.length === 0 ? (
        <p className="py-10 text-center text-sm text-slate-500">
          {search ? 'Nada corresponde a essa busca.' : 'Biblioteca vazia — suba uma faixa acima.'}
        </p>
      ) : (
        <ul className="divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200 dark:divide-slate-800">
          {songs.map((song) => (
            <li key={song.id}>
              <Link
                to={`/song/${song.id}`}
                className="flex items-center gap-4 bg-panel p-4 transition-colors hover:bg-accent-soft"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium tracking-tight">{song.title}</span>
                    <StatusBadge status={song.status} />
                    {/* What is already prepared decides whether a song can go on
                        stage tonight, so it belongs in the list, not one click in. */}
                    {song.lyricsStatus === 'ready' && <Chip>letra</Chip>}
                    {song.stemsStatus === 'ready' && <Chip>pistas</Chip>}
                  </div>
                  <p className="truncate text-xs text-slate-500">
                    {song.artist || 'Sem artista'}
                    {song.keyName && ` · ${song.keyName}`}
                    {song.bpm ? ` · ${Math.round(song.bpm)} BPM` : ''}
                    {song.duration ? ` · ${formatTime(song.duration)}` : ''}
                  </p>
                  {song.status === 'failed' && song.error && (
                    <p className="truncate text-xs text-rose-500">{song.error}</p>
                  )}
                </div>
                <span className="shrink-0 text-xs text-slate-400">abrir →</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
