import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import * as api from '../lib/api'
import type { Song, Stem } from '../lib/api'
import { displayLabel } from '../components/ChordGrid'
import { KaraokeView } from '../components/KaraokeView'
import { StemMixer } from '../components/StemMixer'
import { useStemPlayer } from '../hooks/useStemPlayer'

/**
 * The stage view.
 *
 * Everything here is subordinate to one question: what does someone need on a
 * music stand, two metres away, while singing? So the lyric is the page, the
 * chrome hides itself, the screen is kept awake, and nothing is loaded from the
 * network after playback starts — the stems are already decoded in memory
 * before the transport will let you press play.
 */
export function PerformancePage() {
  const { songId = '' } = useParams()
  const [song, setSong] = useState<Song | null>(null)
  const [stems, setStems] = useState<Stem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [showMixer, setShowMixer] = useState(false)
  const [transpose, setTranspose] = useState(0)

  const player = useStemPlayer(stems)

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
    <div className="fixed inset-0 flex flex-col bg-slate-950 text-slate-200">
      <header className="flex items-center justify-between gap-4 px-6 py-3 text-sm">
        <div className="min-w-0">
          <p className="truncate font-semibold text-white">{song.title}</p>
          <p className="truncate text-xs text-slate-500">
            {song.artist || 'Sem artista'}
            {song.analysis ? ` · ${song.analysis.key.name} · ${Math.round(song.analysis.bpm)} BPM` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Stepper value={transpose} onChange={setTranspose} />
          <button
            type="button"
            onClick={() => setShowMixer((previous) => !previous)}
            className="rounded-full border border-slate-700 px-4 py-1.5 text-xs font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
          >
            Mixer
          </button>
          <Link
            to={`/song/${song.id}`}
            className="rounded-full border border-slate-700 px-4 py-1.5 text-xs font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
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
            onSeek={player.seek}
          />
        ) : (
          <div className="flex h-full items-center justify-center px-8 text-center text-slate-500">
            Esta música ainda não tem letra transcrita.
          </div>
        )}
      </main>

      <footer className="border-t border-slate-800 px-6 py-4">
        {!player.ready && (
          <p className="mb-2 text-center text-xs text-slate-500">
            {player.error
              ? player.error
              : `Carregando as pistas… ${Math.round(player.loaded * 100)}%`}
          </p>
        )}
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={player.toggle}
            disabled={!player.ready}
            className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-white text-slate-950 transition hover:bg-slate-200 disabled:opacity-30"
            aria-label={player.playing ? 'Pausar' : 'Tocar'}
          >
            {player.playing ? (
              <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
                <rect x="4" y="3" width="4" height="14" rx="1" fill="currentColor" />
                <rect x="12" y="3" width="4" height="14" rx="1" fill="currentColor" />
              </svg>
            ) : (
              <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
                <path d="M5 3.5 16 10 5 16.5Z" fill="currentColor" />
              </svg>
            )}
          </button>
          <span className="w-12 shrink-0 text-xs tabular-nums text-slate-500">
            {formatTime(player.currentTime)}
          </span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.001}
            value={progress}
            onChange={(event) => player.seek(Number(event.target.value) * player.duration)}
            className="h-1 w-full accent-sky-400"
            aria-label="Posição"
          />
          <span className="w-12 shrink-0 text-right text-xs tabular-nums text-slate-500">
            {formatTime(player.duration)}
          </span>
        </div>
      </footer>
    </div>
  )
}

function Stepper({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return (
    <div className="flex items-center gap-1 rounded-full border border-slate-700 px-2 py-1">
      <button
        type="button"
        onClick={() => onChange(Math.max(-11, value - 1))}
        className="px-1.5 text-slate-400 hover:text-white"
        aria-label="Baixar meio tom"
      >
        −
      </button>
      <span className="w-10 text-center text-xs tabular-nums text-slate-300">
        {value > 0 ? `+${value}` : value}
      </span>
      <button
        type="button"
        onClick={() => onChange(Math.min(11, value + 1))}
        className="px-1.5 text-slate-400 hover:text-white"
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
