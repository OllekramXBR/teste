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
    ready: 'ready',
    failed: 'failed',
    analyzing: 'analysing…',
    pending: 'queued',
  }
  return (
    <span className={`rounded px-2 py-0.5 text-[10px] font-semibold ${styles[status]}`}>
      {labels[status]}
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
        className={`cursor-pointer rounded-2xl border-2 border-dashed p-8 text-center transition-colors ${
          dragging
            ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/30'
            : 'border-slate-300 hover:border-indigo-400 dark:border-slate-600'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".mp3,.wav,.flac,.ogg,.oga,.aiff,.aif,audio/*"
          multiple
          className="hidden"
          onChange={(event) => {
            if (event.target.files?.length) void upload(event.target.files)
            event.target.value = ''
          }}
        />
        <p className="text-base font-semibold">Drop an audio file to get its chords</p>
        <p className="mt-1 text-xs text-slate-500">
          MP3, WAV, FLAC, OGG or AIFF · analysed locally, nothing leaves your machine
        </p>
        {progress !== null && (
          <div className="mx-auto mt-4 h-1.5 w-56 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
            <div
              className="h-full bg-indigo-500 transition-all"
              style={{ width: `${Math.round(progress * 100)}%` }}
            />
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <label htmlFor="artist" className="text-xs text-slate-500">
          Artist for the next upload
        </label>
        <input
          id="artist"
          value={artist}
          onChange={(event) => setArtist(event.target.value)}
          placeholder="optional"
          className="flex-1 rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-600 dark:bg-slate-800"
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
        <h1 className="text-3xl font-bold">Chords for any track you own</h1>
        <p className="mt-2 text-sm text-slate-500">
          Upload a file and Chordsmith finds the beats, the key and the chords, then plays them back
          in time with the music.
        </p>
      </header>

      <Uploader onUploaded={(song) => setSongs((previous) => [song, ...(previous ?? [])])} />

      <div className="flex items-center gap-3">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search your library"
          className="flex-1 rounded border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800"
        />
      </div>

      {error && <p className="text-sm text-rose-500">{error}</p>}

      {songs === null ? (
        <p className="text-center text-sm text-slate-500">Loading your library…</p>
      ) : songs.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-500">
          {search ? 'Nothing matches that search.' : 'Your library is empty — upload a track above.'}
        </p>
      ) : (
        <ul className="divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200 dark:divide-slate-700 dark:border-slate-700">
          {songs.map((song) => (
            <li key={song.id}>
              <Link
                to={`/song/${song.id}`}
                className="flex items-center gap-4 bg-white p-4 transition-colors hover:bg-slate-50 dark:bg-slate-800/60 dark:hover:bg-slate-700/60"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-semibold">{song.title}</span>
                    <StatusBadge status={song.status} />
                  </div>
                  <p className="truncate text-xs text-slate-500">
                    {song.artist || 'Unknown artist'}
                    {song.keyName && ` · ${song.keyName}`}
                    {song.bpm ? ` · ${Math.round(song.bpm)} BPM` : ''}
                    {song.duration ? ` · ${formatTime(song.duration)}` : ''}
                  </p>
                  {song.status === 'failed' && song.error && (
                    <p className="truncate text-xs text-rose-500">{song.error}</p>
                  )}
                </div>
                <span className="text-xs text-slate-400">open →</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
