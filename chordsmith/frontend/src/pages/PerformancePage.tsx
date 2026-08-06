import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import * as api from '../lib/api'
import type { Setlist, Song, Stem } from '../lib/api'
import { displayLabel } from '../components/ChordGrid'
import { KaraokeView } from '../components/KaraokeView'
import { StemMixer } from '../components/StemMixer'
import { useStemPlayer } from '../hooks/useStemPlayer'

/**
 * The stage view, designed for a tablet held by someone whose hands are on a
 * guitar.
 *
 * That premise decides nearly everything here. Every control is a touch target
 * rather than a click target, and none of them depends on hover, which does not
 * exist on the device this runs on. The transport sits at the bottom corners
 * where a thumb reaches without letting go of the neck. Text cannot be selected
 * and double-tap cannot zoom, because both are what actually happens when a
 * guitarist brushes the screen mid-song. And there is a lock, because the most
 * likely input during a performance is an accidental one.
 *
 * Nothing is loaded from the network after playback starts: the stems are
 * decoded into memory before the transport will let anyone press play.
 */
export function PerformancePage() {
  const { songId = '' } = useParams()
  const [params] = useSearchParams()
  const setlistId = params.get('setlist')
  const [setlist, setSetlist] = useState<Setlist | null>(null)
  const [song, setSong] = useState<Song | null>(null)
  const [stems, setStems] = useState<Stem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [showMixer, setShowMixer] = useState(false)
  const [transpose, setTranspose] = useState(0)
  const [locked, setLocked] = useState(false)

  const [variantState, setVariantState] = useState<'original' | 'rendering' | 'ready'>('original')

  // Transposition swaps the audio for a pre-rendered copy in the new key rather
  // than shifting pitch during playback. Until that copy exists the original
  // keeps playing, and the header says so — a chart in one key over a recording
  // in another is the one thing worse than no transposition at all.
  const playing = useMemo(() => {
    if (transpose === 0 || variantState !== 'ready') return stems
    const key = api.variantKey(transpose)
    return stems.map((stem) => ({ ...stem, url: api.variantStemUrl(songId, key, stem.name) }))
  }, [stems, transpose, variantState, songId])

  const player = useStemPlayer(playing)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const [fetched, stemResponse] = await Promise.all([
          api.getSong(songId),
          api.getStems(songId).catch(() => ({ status: 'none' as const, error: null, stems: [] })),
        ])
        if (cancelled) return
        setSong(fetched)
        setStems(stemResponse.stems)
      } catch (loadError) {
        if (cancelled) return
        setError(loadError instanceof Error ? loadError.message : 'Não consegui abrir esta música')
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [songId])

  useEffect(() => {
    if (!setlistId) return
    let cancelled = false
    api
      .getSetlist(setlistId)
      .then((fetched) => !cancelled && setSetlist(fetched))
      .catch(() => !cancelled && setSetlist(null))
    return () => {
      cancelled = true
    }
  }, [setlistId])

  useEffect(() => {
    if (transpose === 0 || !stems.length) {
      setVariantState('original')
      return
    }
    let cancelled = false
    let timer: number | undefined

    const ask = async () => {
      try {
        const response = await api.renderVariant(songId, transpose)
        if (cancelled) return
        if (response.status === 'ready') {
          setVariantState('ready')
          return
        }
        setVariantState('rendering')
        // A few minutes of phase vocoder per stem; polling slowly costs nothing
        // and the answer only changes once.
        timer = window.setTimeout(ask, 15000)
      } catch {
        if (!cancelled) setVariantState('original')
      }
    }

    void ask()
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [songId, transpose, stems.length])

  const position = setlist?.songs.findIndex((entry) => entry.id === songId) ?? -1
  const nextSong = position >= 0 ? setlist?.songs[position + 1] : undefined

  // Pull the next song's stems into the browser cache while this one plays.
  // Five files is enough of a wait to be noticeable between songs, and the gap
  // between two songs in a set is the one moment nobody wants to fill.
  useEffect(() => {
    if (!nextSong) return
    let cancelled = false
    void api
      .getStems(nextSong.id)
      .then((response) => {
        if (cancelled) return
        for (const stem of response.stems) void fetch(stem.url).catch(() => undefined)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [nextSong])

  // A phone that sleeps in the middle of the second verse is worse than no
  // screen at all. The lock is released automatically when the page goes away.
  useEffect(() => {
    let sentinel: WakeLockSentinel | null = null
    const request = async () => {
      try {
        sentinel = await navigator.wakeLock?.request('screen')
      } catch {
        // Unsupported or denied: the show goes on, the screen may dim.
      }
    }
    void request()
    const onVisibility = () => {
      if (document.visibilityState === 'visible') void request()
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      void sentinel?.release()
    }
  }, [])

  const chords = useMemo(() => {
    const analysis = song?.analysis
    if (!analysis) return []
    return analysis.chords
      .filter((chord) => chord.root !== null)
      .map((chord) => ({
        label: displayLabel(chord.label, transpose, 0, analysis.useFlats),
        start: chord.start,
      }))
  }, [song, transpose])

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if ((event.target as HTMLElement | null)?.tagName === 'INPUT') return
      if (event.code === 'Space') {
        event.preventDefault()
        player.toggle()
      }
      if (event.code === 'ArrowLeft') player.seek(player.currentTime - 5)
      if (event.code === 'ArrowRight') player.seek(player.currentTime + 5)
    },
    [player],
  )

  useEffect(() => {
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onKeyDown])

  if (error) return <Stage><p className="text-rose-400">{error}</p></Stage>
  if (!song) return <Stage><p className="text-slate-500">Carregando…</p></Stage>

  if (!stems.length) {
    return (
      <Stage>
        <h1 className="text-2xl font-semibold text-white">{song.title}</h1>
        <p className="max-w-md text-center text-slate-400">
          O modo palco toca as pistas separadas, para tirar a voz principal e deixar você cantar.
          Esta música ainda não foi separada.
        </p>
        <Link to={`/song/${song.id}`} className="text-sm text-indigo-400 hover:underline">
          Voltar e separar as pistas
        </Link>
      </Stage>
    )
  }

  const lyrics = song.lyrics
  const progress = player.duration ? player.currentTime / player.duration : 0

  return (
    <div className="fixed inset-0 flex touch-manipulation select-none flex-col bg-slate-950 text-slate-200">
      <header className="flex items-center justify-between gap-4 px-5 py-2.5 text-sm">
        <div className="min-w-0">
          <p className="truncate font-semibold text-white">{song.title}</p>
          <p className="truncate text-xs text-slate-500">
            {setlist && position >= 0 ? `${position + 1}/${setlist.songs.length} · ` : ''}
            {song.artist || 'Sem artista'}
            {song.analysis ? ` · ${song.analysis.key.name} · ${Math.round(song.analysis.bpm)} BPM` : ''}
          </p>
          {transpose !== 0 && (
            <p
              className={[
                'truncate text-xs',
                variantState === 'ready' ? 'text-emerald-400' : 'text-amber-400',
              ].join(' ')}
            >
              {variantState === 'ready'
                ? `áudio transposto ${transpose > 0 ? '+' : ''}${transpose}`
                : 'grade transposta — o áudio ainda está no tom original, renderizando…'}
            </p>
          )}
        </div>
        <div className={locked ? 'pointer-events-none opacity-30' : 'flex items-center gap-2'}>
          <Stepper value={transpose} onChange={setTranspose} />
          <StageButton onClick={() => setShowMixer((previous) => !previous)} active={showMixer}>
            Mixer
          </StageButton>
          {nextSong && (
            <Link
              to={`/song/${nextSong.id}/perform?setlist=${setlistId}`}
              className="flex h-11 items-center rounded-full border border-slate-600 px-5 text-sm font-medium text-white"
              title={nextSong.title}
            >
              Próxima →
            </Link>
          )}
          <Link
            to={setlistId ? `/setlists/${setlistId}` : `/song/${song.id}`}
            className="flex h-11 items-center rounded-full border border-slate-700 px-5 text-sm font-medium text-slate-300"
          >
            Sair
          </Link>
        </div>
      </header>

      {showMixer && (
        <div className="mx-6 mb-2 [&>section]:border-slate-800 [&>section]:bg-slate-900">
          <StemMixer
            stems={stems}
            mix={player.mix}
            solo={player.solo}
            onVolume={player.setStemVolume}
            onMute={player.toggleMute}
            onSolo={player.toggleSolo}
          />
        </div>
      )}

      <main className="min-h-0 flex-1">
        {lyrics ? (
          <KaraokeView
            lyrics={lyrics}
            chords={chords}
            currentTime={player.currentTime}
            performance
            onSeek={locked ? undefined : player.seek}
          />
        ) : (
          <div className="flex h-full items-center justify-center px-8 text-center text-slate-500">
            Esta música ainda não tem letra transcrita.
          </div>
        )}
      </main>

      {/* The transport lives at the bottom edge, where a thumb reaches without
          letting go of the neck of the guitar. Everything in it is at least 56px
          across, which is the smallest thing a finger hits reliably while the
          other hand is busy. */}
      <footer className="border-t border-slate-800 px-5 pb-5 pt-3">
        {!player.ready && (
          <p className="mb-2 text-center text-sm text-slate-500">
            {player.error
              ? player.error
              : `Carregando as pistas… ${Math.round(player.loaded * 100)}%`}
          </p>
        )}
        <div className="mb-3 flex items-center gap-3">
          <span className="w-12 shrink-0 text-xs tabular-nums text-slate-500">
            {formatTime(player.currentTime)}
          </span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.001}
            value={progress}
            disabled={locked}
            onChange={(event) => player.seek(Number(event.target.value) * player.duration)}
            className="w-full text-sky-400 disabled:opacity-40"
            aria-label="Posição"
          />
          <span className="w-12 shrink-0 text-right text-xs tabular-nums text-slate-500">
            {formatTime(player.duration)}
          </span>
        </div>

        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => setLocked((previous) => !previous)}
            className={[
              'flex h-14 w-14 shrink-0 items-center justify-center rounded-full border text-xs font-semibold',
              locked
                ? 'border-amber-400 bg-amber-400 text-slate-950'
                : 'border-slate-700 text-slate-400',
            ].join(' ')}
            aria-pressed={locked}
            aria-label={locked ? 'Destravar a tela' : 'Travar a tela'}
          >
            {locked ? 'TRAV' : 'LIVRE'}
          </button>

          <div className="flex items-center gap-3">
            <SeekButton
              label="Voltar 10 segundos"
              disabled={locked}
              onClick={() => player.seek(player.currentTime - 10)}
            >
              −10
            </SeekButton>
            <button
              type="button"
              onClick={player.toggle}
              disabled={!player.ready || locked}
              className="flex h-20 w-20 shrink-0 items-center justify-center rounded-full bg-white text-slate-950 active:bg-slate-300 disabled:opacity-30"
              aria-label={player.playing ? 'Pausar' : 'Tocar'}
            >
              {player.playing ? (
                <svg width="28" height="28" viewBox="0 0 20 20" aria-hidden="true">
                  <rect x="4" y="3" width="4" height="14" rx="1" fill="currentColor" />
                  <rect x="12" y="3" width="4" height="14" rx="1" fill="currentColor" />
                </svg>
              ) : (
                <svg width="28" height="28" viewBox="0 0 20 20" aria-hidden="true">
                  <path d="M5 3.5 16 10 5 16.5Z" fill="currentColor" />
                </svg>
              )}
            </button>
            <SeekButton
              label="Avançar 10 segundos"
              disabled={locked}
              onClick={() => player.seek(player.currentTime + 10)}
            >
              +10
            </SeekButton>
          </div>

          <div className="w-14 shrink-0" />
        </div>
      </footer>
    </div>
  )
}

function StageButton({
  children,
  onClick,
  active,
}: {
  children: React.ReactNode
  onClick: () => void
  active?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={[
        'h-11 rounded-full border px-5 text-sm font-medium',
        active ? 'border-white bg-white text-slate-950' : 'border-slate-700 text-slate-300',
      ].join(' ')}
    >
      {children}
    </button>
  )
}

function SeekButton({
  children,
  label,
  disabled,
  onClick,
}: {
  children: React.ReactNode
  label: string
  disabled: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className="h-14 w-14 shrink-0 rounded-full border border-slate-700 text-sm font-semibold text-slate-300 active:bg-slate-800 disabled:opacity-30"
    >
      {children}
    </button>
  )
}

function Stepper({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return (
    <div className="flex items-center rounded-full border border-slate-700">
      <button
        type="button"
        onClick={() => onChange(Math.max(-11, value - 1))}
        className="h-11 w-11 rounded-l-full text-lg text-slate-300 active:bg-slate-800"
        aria-label="Baixar meio tom"
      >
        −
      </button>
      <span className="w-10 text-center text-sm tabular-nums text-slate-300">
        {value > 0 ? `+${value}` : value}
      </span>
      <button
        type="button"
        onClick={() => onChange(Math.min(11, value + 1))}
        className="h-11 w-11 rounded-r-full text-lg text-slate-300 active:bg-slate-800"
        aria-label="Subir meio tom"
      >
        +
      </button>
    </div>
  )
}

function Stage({ children }: { children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 flex flex-col items-center justify-center gap-4 bg-slate-950 px-6">
      {children}
    </div>
  )
}

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds)) return '0:00'
  const whole = Math.floor(seconds)
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`
}
