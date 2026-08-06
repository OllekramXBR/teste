import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import * as api from '../lib/api'
import type { Song } from '../lib/api'
import { formatTime } from '../components/Transport'
import { LibraryBrowser } from '../components/LibraryBrowser'
import { Page, PageHeader } from '../components/Page'
import { br } from '../lib/brazilian'

const POLL_INTERVAL_MS = 2000
const LAYOUT_KEY = 'metatron.libraryLayout.v1'

function StatusBadge({ status }: { status: Song['status'] }) {
  const styles: Record<Song['status'], string> = {
    ready: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300',
    failed: 'bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300',
    analyzing: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300',
    pending: 'bg-slate-100 text-ink-soft  ',
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

/**
 * The album art, or the song's initial when it has none.
 *
 * A cover that fails to load must not leave a broken-image icon in a list — a
 * beets library embeds art in most files but not all, and half a list of broken
 * pictures looks like the app is broken rather than the tags.
 */
function Cover({ song }: { song: Song }) {
  const [failed, setFailed] = useState(false)
  if (failed) {
    return (
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-slate-200 text-sm font-semibold text-ink-faint ">
        {song.title.trim().charAt(0).toUpperCase() || '♪'}
      </div>
    )
  }
  return (
    <img
      src={`/api/songs/${song.id}/cover`}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
      className="h-11 w-11 shrink-0 rounded-md object-cover"
    />
  )
}

/** The same picture at card size, with the same fallback. */
function CoverLarge({ song }: { song: Song }) {
  const [failed, setFailed] = useState(false)
  if (failed) {
    return (
      <div className="flex h-full w-full items-center justify-center text-3xl font-semibold text-ink-faint">
        {song.title.trim().charAt(0).toUpperCase() || '♪'}
      </div>
    )
  }
  return (
    <img
      src={`/api/songs/${song.id}/cover`}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
      className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
    />
  )
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="shrink-0 rounded-full border border-line px-1.5 py-0.5 text-[10px] text-ink-soft ">
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
            : 'border-line hover:border-accent'
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
        <p className="mt-1.5 text-xs text-ink-soft">
          MP3, WAV, FLAC, OGG, AIFF, M4A · analisado aqui no servidor, nada sai da sua rede
        </p>
        {progress !== null && (
          <div className="mx-auto mt-5 h-1 w-56 overflow-hidden rounded-full bg-canvas">
            <div
              className="h-full bg-accent transition-all"
              style={{ width: `${Math.round(progress * 100)}%` }}
            />
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <label htmlFor="artist" className="shrink-0 text-xs text-ink-soft">
          Artista do próximo envio
        </label>
        <input
          id="artist"
          value={artist}
          onChange={(event) => setArtist(event.target.value)}
          placeholder="opcional"
          className="flex-1 rounded-lg border border-line bg-panel px-2.5 py-1.5 text-sm placeholder:text-ink-faint focus:border-accent focus:outline-none "
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
  // Remembered, because it is a preference about how somebody reads, not a
  // thing they want to re-choose on every visit.
  const [layout, setLayout] = useState<'list' | 'grid'>(
    () => (localStorage.getItem(LAYOUT_KEY) as 'list' | 'grid') || 'list',
  )

  useEffect(() => {
    localStorage.setItem(LAYOUT_KEY, layout)
  }, [layout])

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
    <Page>
      <PageHeader
        centered
        title="Sua música, aberta"
        description="Suba um arquivo e o Metatron acha a batida, o tom e os acordes. Depois transcreve a letra e separa a voz principal da banda, para você cantar por cima da sua própria gravação."
      />

      <Uploader onUploaded={(song) => setSongs((previous) => [song, ...(previous ?? [])])} />

      <LibraryBrowser
        onImported={(song) => setSongs((previous) => [song, ...(previous ?? [])])}
      />

      <div className="flex items-center gap-2">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Buscar na biblioteca"
          className="w-full rounded-lg border border-line bg-panel px-3.5 py-2.5 text-sm transition-colors placeholder:text-ink-faint focus:border-accent focus:outline-none "
        />
        <div className="flex shrink-0 items-center gap-1 rounded-lg bg-slate-200/70 p-1 ">
          {(['list', 'grid'] as const).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setLayout(option)}
              aria-pressed={layout === option}
              title={option === 'list' ? 'Lista' : 'Grade'}
              className={`rounded-md px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                layout === option
                  ? 'bg-panel text-ink shadow-sm dark:text-white'
                  : 'text-ink-soft'
              }`}
            >
              {option === 'list' ? '☰' : '▦'}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-sm text-rose-500">{error}</p>}

      {songs === null ? (
        <p className="text-center text-sm text-ink-soft">Carregando a biblioteca…</p>
      ) : songs.length === 0 ? (
        <p className="py-10 text-center text-sm text-ink-soft">
          {search ? 'Nada corresponde a essa busca.' : 'Biblioteca vazia — suba uma faixa acima.'}
        </p>
      ) : layout === 'grid' ? (
        <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {songs.map((song) => (
            <li key={song.id}>
              <Link to={`/song/${song.id}`} className="group block">
                <div className="aspect-square overflow-hidden rounded-lg bg-canvas">
                  <CoverLarge song={song} />
                </div>
                <p className="mt-2 truncate text-sm font-medium tracking-tight">{song.title}</p>
                <p className="truncate text-xs text-ink-soft">
                  {song.artist || 'Sem artista'}
                  {song.keyName && ` · ${song.keyName}`}
                </p>
                {song.chords?.length ? (
                  <p className="truncate font-mono text-xs text-accent">
                    {song.chords.slice(0, 6).map((chord) => br(chord)).join(' ')}
                  </p>
                ) : null}
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line ">
          {songs.map((song) => (
            <li key={song.id}>
              <Link
                to={`/song/${song.id}`}
                className="flex items-center gap-4 bg-panel p-4 transition-colors hover:bg-accent-soft"
              >
                <Cover song={song} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium tracking-tight">{song.title}</span>
                    <StatusBadge status={song.status} />
                    {/* What is already prepared decides whether a song can go on
                        stage tonight, so it belongs in the list, not one click in. */}
                    {song.lyricsStatus === 'ready' && <Chip>letra</Chip>}
                    {song.stemsStatus === 'ready' && <Chip>pistas</Chip>}
                  </div>
                  <p className="truncate text-xs text-ink-soft">
                    {song.artist || 'Sem artista'}
                    {song.keyName && ` · ${song.keyName}`}
                    {song.bpm ? ` · ${Math.round(song.bpm)} BPM` : ''}
                    {song.duration ? ` · ${formatTime(song.duration)}` : ''}
                  </p>
                  {/* The chords, right in the list. It is the one thing that
                      tells you at a glance whether a song is worth opening,
                      and it costs nothing now that the summary is stored. */}
                  {song.chords?.length ? (
                    <p className="mt-0.5 truncate font-mono text-xs text-accent">
                      {song.chords.map((chord) => br(chord)).join('  ')}
                    </p>
                  ) : null}
                  {song.status === 'failed' && song.error && (
                    <p className="truncate text-xs text-rose-500">{song.error}</p>
                  )}
                </div>
                <span className="shrink-0 text-xs text-ink-faint">abrir →</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Page>
  )
}
