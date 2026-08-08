import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import * as api from '../lib/api'
import type { Song } from '../lib/api'
import { formatTime } from '../components/Transport'
import { QueuePanel } from '../components/QueuePanel'
import { LibraryBrowser } from '../components/LibraryBrowser'
import { Page, PageHeader } from '../components/Page'
import { br } from '../lib/brazilian'
import { getFingerings, INSTRUMENTS } from '../lib/fretboard'
import { parseLabel } from '../lib/theory'

const POLL_INTERVAL_MS = 2000
const LAYOUT_KEY = 'metatron.libraryLayout.v1'

/**
 * Whether a chord comes out in open position on a guitar — no barre, nothing
 * past the fourth fret — using the same search that draws the diagrams, so
 * this badge can never disagree with them. Cached per label: the library
 * repeats the same handful of chords across every song.
 */
const openShapeCache = new Map<string, boolean>()
function isOpenShape(label: string): boolean {
  const cached = openShapeCache.get(label)
  if (cached !== undefined) return cached
  const parsed = parseLabel(label)
  let open = false
  if (parsed) {
    const [best] = getFingerings(parsed.root, parsed.quality, INSTRUMENTS.guitar, 1)
    open = Boolean(best && best.barre === 0 && best.baseFret <= 4)
  }
  openShapeCache.set(label, open)
  return open
}

function isEasySong(song: Song): boolean {
  return Boolean(song.chords?.length && song.chords.every(isOpenShape))
}

/** "G major" from the API → a pill label "G"; "E minor" → "Em". */
function keyPill(keyName: string): string {
  const match = keyName.match(/^([A-G][#b]?)\s+(major|minor)$/)
  if (!match) return keyName
  return match[2] === 'minor' ? `${match[1]}m` : match[1]
}

/** The same name spelt out in Portuguese for the song line. */
function keyNamePt(keyName: string): string {
  const match = keyName.match(/^([A-G][#b]?)\s+(major|minor)$/)
  if (!match) return keyName
  return `${match[1]} ${match[2] === 'minor' ? 'menor' : 'maior'}`
}

function StatusBadge({ status }: { status: Song['status'] }) {
  const styles: Record<Song['status'], string> = {
    ready: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300',
    failed: 'bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300',
    analyzing: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300',
    pending: 'bg-canvas text-ink-soft',
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
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-canvas text-sm font-semibold text-ink-faint ">
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
  const [keyFilter, setKeyFilter] = useState<string | null>(null)
  const [easyOnly, setEasyOnly] = useState(false)
  // Remembered, because it is a preference about how somebody reads, not a
  // thing they want to re-choose on every visit.
  const [layout, setLayout] = useState<'list' | 'grid'>(
    () => (localStorage.getItem(LAYOUT_KEY) as 'list' | 'grid') || 'list',
  )

  // The keys actually present, with counts — a picker of twelve keys where
  // nine are empty is a picker of disappointments.
  const keyOptions = useMemo(() => {
    const counts = new Map<string, number>()
    for (const song of songs ?? []) {
      if (song.keyName && song.status === 'ready') {
        counts.set(song.keyName, (counts.get(song.keyName) ?? 0) + 1)
      }
    }
    return [...counts.entries()]
      .map(([keyName, count]) => ({ keyName, pill: keyPill(keyName), count }))
      .sort((a, b) => b.count - a.count)
  }, [songs])

  const visible = useMemo(() => {
    if (!songs) return null
    return songs.filter(
      (song) =>
        (keyFilter === null || song.keyName === keyFilter) &&
        (!easyOnly || isEasySong(song)),
    )
  }, [songs, keyFilter, easyOnly])

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

      <QueuePanel songs={songs ?? []} onQueued={() => void refresh(search)} />

      <div className="flex items-center gap-2">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Buscar na biblioteca"
          className="w-full rounded-lg border border-line bg-panel px-3.5 py-2.5 text-sm transition-colors placeholder:text-ink-faint focus:border-accent focus:outline-none "
        />
        <div className="flex shrink-0 items-center gap-1 rounded-lg bg-canvas/70 p-1 ">
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

      {/* Filters a player actually uses: which key, and "can I already play
          this" — every chord in open position, no barre. */}
      {(songs?.length ?? 0) > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {keyOptions.length > 1 && (
            <button
              type="button"
              onClick={() => setKeyFilter(null)}
              className={`rounded-full px-3 py-1 font-semibold transition ${
                keyFilter === null
                  ? 'bg-accent text-canvas'
                  : 'border border-line text-ink-soft hover:border-accent hover:text-accent'
              }`}
            >
              todos os tons
            </button>
          )}
          {keyOptions.length > 1 &&
            keyOptions.map((option) => (
            <button
              key={option.keyName}
              type="button"
              onClick={() =>
                setKeyFilter((previous) => (previous === option.keyName ? null : option.keyName))
              }
              className={`rounded-full px-3 py-1 font-semibold transition ${
                keyFilter === option.keyName
                  ? 'bg-accent text-canvas'
                  : 'border border-line text-ink-soft hover:border-accent hover:text-accent'
              }`}
            >
              {option.pill}
              <span className="ml-1 opacity-60">{option.count}</span>
            </button>
          ))}
          <button
            type="button"
            onClick={() => setEasyOnly((previous) => !previous)}
            aria-pressed={easyOnly}
            title="Só músicas em que todo acorde sai em posição aberta, sem pestana"
            className={`ml-auto rounded-full px-3 py-1 font-semibold transition ${
              easyOnly
                ? 'bg-emerald-500 text-white'
                : 'border border-line text-ink-soft hover:border-emerald-500 hover:text-emerald-500'
            }`}
          >
            fáceis no violão
          </button>
        </div>
      )}

      {error && <p className="text-sm text-rose-500">{error}</p>}

      {visible === null ? (
        <p className="text-center text-sm text-ink-soft">Carregando a biblioteca…</p>
      ) : visible.length === 0 ? (
        <p className="py-10 text-center text-sm text-ink-soft">
          {search || keyFilter || easyOnly
            ? 'Nada corresponde a esses filtros.'
            : 'Biblioteca vazia — suba uma faixa acima.'}
        </p>
      ) : layout === 'grid' ? (
        <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {visible.map((song) => (
            <li key={song.id}>
              <Link to={`/song/${song.id}`} className="group block">
                <div className="aspect-square overflow-hidden rounded-lg bg-canvas">
                  <CoverLarge song={song} />
                </div>
                <p className="mt-2 truncate text-sm font-medium tracking-tight">{song.title}</p>
                <p className="truncate text-xs text-ink-soft">
                  {song.artist || 'Sem artista'}
                  {song.keyName && ` · ${keyNamePt(song.keyName)}`}
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
        <ul className="divide-y divide-[var(--color-line)] overflow-hidden rounded-xl border border-line ">
          {visible.map((song) => (
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
                    {isEasySong(song) && (
                      <span className="shrink-0 rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300">
                        fácil
                      </span>
                    )}
                  </div>
                  <p className="truncate text-xs text-ink-soft">
                    {song.artist || 'Sem artista'}
                    {song.keyName && ` · ${keyNamePt(song.keyName)}`}
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
