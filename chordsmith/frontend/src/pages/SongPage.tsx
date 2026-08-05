import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import * as api from '../lib/api'
import type { Analysis, Song } from '../lib/api'
import { AudioEngine, voiceChord } from '../lib/audioEngine'
import { INSTRUMENTS } from '../lib/fretboard'
import { mod12, parseLabel, QUALITY_LABELS, romanNumeral } from '../lib/theory'
import { usePlayer } from '../hooks/usePlayer'
import { ChordGrid, displayLabel, groupIntoBars } from '../components/ChordGrid'
import { ChordSheet } from '../components/ChordSheet'
import { ChordToneLegend, FretDiagram } from '../components/FretDiagram'
import { PianoDiagram } from '../components/PianoDiagram'
import { LeadSummary, TabStaff } from '../components/TabStaff'
import { Toolbar, type ToolbarSettings } from '../components/Toolbar'
import { Transport } from '../components/Transport'
import { Tuner } from '../components/Tuner'

type View = 'chords' | 'tab' | 'both'

const SETTINGS_KEY = 'chordsmith.settings.v1'
const POLL_INTERVAL_MS = 1500

const DEFAULT_SETTINGS: ToolbarSettings = {
  transpose: 0,
  capo: 0,
  rate: 1,
  songVolume: 0.85,
  chordVolume: 0,
  clickVolume: 0,
  instrument: 'guitar',
  autoScroll: true,
}

function loadSettings(): ToolbarSettings {
  try {
    const stored = localStorage.getItem(SETTINGS_KEY)
    if (!stored) return DEFAULT_SETTINGS
    return { ...DEFAULT_SETTINGS, ...(JSON.parse(stored) as Partial<ToolbarSettings>) }
  } catch {
    return DEFAULT_SETTINGS
  }
}

/** Index of the beat the playhead currently sits on, or -1 before the first. */
function findActiveBeat(analysis: Analysis | null | undefined, time: number): number {
  if (!analysis || !analysis.beats.length) return -1
  const beats = analysis.beats
  let low = 0
  let high = beats.length - 1
  let result = -1
  while (low <= high) {
    const middle = (low + high) >> 1
    if (beats[middle].time <= time) {
      result = middle
      low = middle + 1
    } else {
      high = middle - 1
    }
  }
  return result
}

export function SongPage() {
  const { songId = '' } = useParams()
  const navigate = useNavigate()

  const [song, setSong] = useState<Song | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [settings, setSettings] = useState<ToolbarSettings>(loadSettings)
  const [loopBars, setLoopBars] = useState<{ start: number; end: number } | null>(null)
  const [shapeVariant, setShapeVariant] = useState(0)
  const [view, setView] = useState<View>('chords')

  const engineRef = useRef<AudioEngine | null>(null)
  if (engineRef.current === null) engineRef.current = new AudioEngine()
  const engine = engineRef.current

  const analysis = song?.analysis ?? null
  const audioUrl = song ? song.audioUrl : null
  const player = usePlayer(audioUrl)

  // Refs the scheduler reads; it runs on a timer, outside the render cycle.
  const settingsRef = useRef(settings)
  settingsRef.current = settings
  const analysisRef = useRef(analysis)
  analysisRef.current = analysis

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    const poll = async () => {
      try {
        const fetched = await api.getSong(songId)
        if (cancelled) return
        setSong(fetched)
        setLoadError(null)
        if (fetched.status === 'pending' || fetched.status === 'analyzing') {
          timer = window.setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch (error) {
        if (cancelled) return
        setLoadError(error instanceof Error ? error.message : 'Could not load this song')
      }
    }

    void poll()
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [songId])

  useEffect(() => {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings))
  }, [settings])

  useEffect(() => {
    player.setVolume(settings.songVolume)
  }, [player, settings.songVolume])

  useEffect(() => {
    player.setRate(settings.rate)
    engine.reset()
  }, [player, engine, settings.rate])

  useEffect(() => {
    engine.setChordVolume(settings.chordVolume)
  }, [engine, settings.chordVolume])

  useEffect(() => {
    engine.setClickVolume(settings.clickVolume)
  }, [engine, settings.clickVolume])

  useEffect(() => () => engine.dispose(), [engine])

  const bars = useMemo(() => (analysis ? groupIntoBars(analysis.beats) : []), [analysis])

  const loopRegion = useMemo(() => {
    if (!loopBars || !bars.length) return null
    const first = bars.find((bar) => bar.number === loopBars.start)
    const last = bars.find((bar) => bar.number === loopBars.end)
    if (!first || !last) return null
    return { start: first.start, end: last.end }
  }, [loopBars, bars])

  useEffect(() => {
    player.setLoop(loopRegion)
    engine.reset()
  }, [player, engine, loopRegion])

  // Schedule the chord track and metronome ahead of the audio clock.
  useEffect(() => {
    if (!player.playing || !analysis) {
      engine.stop()
      return
    }
    void engine.resume()

    engine.start(() => {
      const audio = player.audioRef.current
      const current = analysisRef.current
      const active = settingsRef.current
      if (!audio || !current) return { chords: [], clicks: [], audioTimeOffset: 0 }

      const songTime = audio.currentTime
      const rate = audio.playbackRate || 1
      const now = engine.currentTime
      const horizon = songTime + 0.6 * rate
      const toAudioTime = (time: number) => now + (time - songTime) / rate

      const upcoming = current.beats.filter(
        (beat) => beat.time >= songTime - 0.05 && beat.time <= horizon,
      )
      const voice = active.instrument === 'piano' ? 'piano' : active.instrument

      return {
        chords: upcoming
          .filter((beat) => beat.root !== null)
          .map((beat) => ({
            key: `chord-${beat.index}-${active.transpose}`,
            time: toAudioTime(beat.time),
            notes: voiceChord(
              mod12(beat.root! + active.transpose),
              beat.notes.map((note) => mod12(note + active.transpose)),
            ),
            voice,
          })),
        clicks: upcoming.map((beat) => ({
          key: `click-${beat.index}`,
          time: toAudioTime(beat.time),
          accented: beat.downbeat,
        })),
        audioTimeOffset: 0,
      }
    })

    return () => engine.stop()
  }, [player.playing, player.audioRef, analysis, engine])

  // Space toggles playback the way every other player does.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target && ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName)) return
      if (event.code === 'Space') {
        event.preventDefault()
        player.toggle()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [player])

  const activeBeatIndex = findActiveBeat(analysis, player.currentTime)
  const activeBeat = activeBeatIndex >= 0 ? analysis?.beats[activeBeatIndex] : undefined

  const handleSettings = useCallback((patch: Partial<ToolbarSettings>) => {
    setSettings((previous) => ({ ...previous, ...patch }))
  }, [])

  const handleBarSelect = useCallback((barNumber: number, extend: boolean) => {
    setLoopBars((previous) => {
      if (!extend || !previous) return { start: barNumber, end: barNumber }
      return barNumber >= previous.start
        ? { start: previous.start, end: barNumber }
        : { start: barNumber, end: previous.end }
    })
  }, [])

  const handleSeek = useCallback(
    (time: number) => {
      player.seek(time)
      engine.reset()
    },
    [player, engine],
  )

  const handleDelete = useCallback(async () => {
    if (!song || !window.confirm(`Delete "${song.title}" and its analysis?`)) return
    await api.deleteSong(song.id)
    navigate('/')
  }, [song, navigate])

  const handleReanalyze = useCallback(async () => {
    if (!song) return
    const updated = await api.reanalyze(song.id)
    setSong({ ...song, ...updated, analysis: null })
  }, [song])

  if (loadError) {
    return (
      <Centered>
        <p className="text-rose-500">{loadError}</p>
        <Link to="/" className="text-sm text-indigo-500 hover:underline">
          Back to the library
        </Link>
      </Centered>
    )
  }

  if (!song) return <Centered>Loading…</Centered>

  if (song.status === 'failed') {
    return (
      <Centered>
        <h2 className="text-lg font-semibold">Analysis failed</h2>
        <p className="max-w-md text-center text-sm text-slate-500">{song.error}</p>
        <button
          type="button"
          onClick={handleReanalyze}
          className="rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500"
        >
          Try again
        </button>
      </Centered>
    )
  }

  if (song.status !== 'ready' || !analysis) {
    return (
      <Centered>
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-slate-300 border-t-indigo-600" />
        <h2 className="text-lg font-semibold">Detecting beats and chords…</h2>
        <p className="text-sm text-slate-500">
          {song.title} — this usually takes a few seconds per minute of audio.
        </p>
      </Centered>
    )
  }

  const displayedChord = activeBeat
    ? displayLabel(activeBeat.label, settings.transpose, settings.capo, analysis.useFlats)
    : ''
  const parsedChord = parseLabel(displayedChord)
  const soundingChord = activeBeat
    ? displayLabel(activeBeat.label, settings.transpose, 0, analysis.useFlats)
    : ''

  return (
    <div className="mx-auto max-w-6xl space-y-5 px-4 py-6 print:px-0 print:py-0">
      <div className="print:hidden">
        <Link to="/" className="text-xs text-slate-500 hover:text-indigo-500">
          ← Library
        </Link>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">{song.title}</h1>
            <p className="text-sm text-slate-500">
              {song.artist || 'Unknown artist'} · {analysis.key.name} ·{' '}
              {Math.round(analysis.bpm)} BPM · {analysis.beatsPerBar}/4 ·{' '}
              {analysis.chords.length} chord changes
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a
              href={api.midiUrl(song.id, settings.transpose)}
              className="rounded border border-slate-300 px-3 py-1.5 text-xs font-semibold hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-700"
            >
              Download MIDI
            </a>
            <button
              type="button"
              onClick={() => window.print()}
              className="rounded border border-slate-300 px-3 py-1.5 text-xs font-semibold hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-700"
            >
              Chord sheet (PDF)
            </button>
            <button
              type="button"
              onClick={handleReanalyze}
              className="rounded border border-slate-300 px-3 py-1.5 text-xs font-semibold hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-700"
            >
              Re-analyse
            </button>
            <button
              type="button"
              onClick={handleDelete}
              className="rounded border border-rose-300 px-3 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-50 dark:border-rose-700 dark:hover:bg-rose-950/40"
            >
              Delete
            </button>
          </div>
        </div>
      </div>

      {player.error && (
        <p className="rounded bg-rose-100 p-2 text-sm text-rose-700 print:hidden dark:bg-rose-950/50 dark:text-rose-300">
          {player.error}
        </p>
      )}

      <div className="print:hidden">
        <Transport
          playing={player.playing}
          currentTime={player.currentTime}
          duration={player.duration || analysis.duration}
          beats={analysis.beats}
          loopRegion={loopRegion}
          onToggle={player.toggle}
          onSeek={handleSeek}
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_260px] print:hidden">
        <div className="space-y-4">
          <Toolbar
            settings={settings}
            onChange={handleSettings}
            keyTonic={analysis.key.tonic}
            keyMode={analysis.key.mode}
            useFlats={analysis.useFlats}
            loopBars={loopBars}
            onClearLoop={() => setLoopBars(null)}
          />
          {settings.transpose !== 0 && (
            <p className="rounded bg-amber-100 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
              The chart is transposed {settings.transpose > 0 ? '+' : ''}
              {settings.transpose} semitones, but the recording still plays in{' '}
              {analysis.key.name}. Turn the song volume down and the chord volume up to hear the
              transposed harmony.
            </p>
          )}
          <div className="flex items-center gap-1 rounded-lg bg-slate-200 p-1 dark:bg-slate-700">
            {(['chords', 'tab', 'both'] as View[]).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setView(option)}
                className={`flex-1 rounded px-3 py-1.5 text-xs font-semibold capitalize transition-colors ${
                  view === option
                    ? 'bg-white text-slate-900 shadow dark:bg-slate-900 dark:text-white'
                    : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-200'
                }`}
              >
                {option === 'tab' ? `Tab (${analysis.lead.notes.length} notes)` : option}
              </button>
            ))}
          </div>

          {(view === 'chords' || view === 'both') && (
            <ChordGrid
              beats={analysis.beats}
              beatsPerBar={analysis.beatsPerBar}
              activeBeat={activeBeatIndex}
              transpose={settings.transpose}
              capo={settings.capo}
              useFlats={analysis.useFlats}
              loopBars={loopBars}
              onSeek={handleSeek}
              onBarSelect={handleBarSelect}
              autoScroll={settings.autoScroll && view !== 'both'}
            />
          )}

          {(view === 'tab' || view === 'both') && (
            <>
              <LeadSummary lead={analysis.lead} onSeek={handleSeek} />
              <TabStaff
                lead={analysis.lead}
                bars={bars}
                currentTime={player.currentTime}
                onSeek={handleSeek}
                autoScroll={settings.autoScroll}
              />
            </>
          )}
        </div>

        <aside className="space-y-4">
          <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800/70">
            <div className="mb-2 flex items-baseline justify-between">
              <h3 className="text-sm font-semibold">Now playing</h3>
              {parsedChord && (
                <span className="text-[10px] uppercase tracking-wide text-slate-400">
                  {QUALITY_LABELS[parsedChord.quality]}
                </span>
              )}
            </div>
            <div className="mb-3 text-4xl font-bold text-indigo-600 dark:text-indigo-400">
              {displayedChord || '—'}
            </div>
            {settings.capo > 0 && soundingChord && (
              <p className="mb-2 text-[11px] text-slate-500">
                sounds as {soundingChord} with the capo on fret {settings.capo}
              </p>
            )}
            {parsedChord && (
              <>
                {settings.instrument === 'piano' ? (
                  <PianoDiagram
                    root={parsedChord.root}
                    notes={[parsedChord.root, ...(activeBeat?.notes ?? [])].map((note) =>
                      mod12(note),
                    )}
                    useFlats={analysis.useFlats}
                    width={216}
                  />
                ) : (
                  <div className="flex flex-col items-center gap-2">
                    <FretDiagram
                      root={parsedChord.root}
                      quality={parsedChord.quality}
                      instrument={INSTRUMENTS[settings.instrument]}
                      useFlats={analysis.useFlats}
                      variant={shapeVariant}
                      width={150}
                    />
                    <button
                      type="button"
                      onClick={() => setShapeVariant((previous) => (previous + 1) % 4)}
                      className="text-[11px] text-indigo-500 hover:underline"
                    >
                      other shape ({shapeVariant + 1}/4)
                    </button>
                  </div>
                )}
                <div className="mt-2">
                  <ChordToneLegend quality={parsedChord.quality} />
                </div>
              </>
            )}
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800/70">
            <h3 className="mb-2 text-sm font-semibold">Chords in this song</h3>
            <div className="flex flex-wrap gap-1.5">
              {analysis.uniqueChords.map((label) => {
                const shown = displayLabel(label, settings.transpose, settings.capo, analysis.useFlats)
                const parsed = parseLabel(
                  displayLabel(label, settings.transpose, 0, analysis.useFlats),
                )
                const numeral = parsed
                  ? romanNumeral(
                      parsed.root,
                      parsed.quality,
                      mod12(analysis.key.tonic + settings.transpose),
                      analysis.key.mode,
                    )
                  : null
                return (
                  <span
                    key={label}
                    title={numeral ? `${numeral} in the key` : 'borrowed from outside the key'}
                    className="rounded bg-slate-100 px-2 py-1 text-xs font-semibold dark:bg-slate-700"
                  >
                    {shown}
                    {numeral && <span className="ml-1 text-[9px] text-slate-400">{numeral}</span>}
                  </span>
                )
              })}
            </div>
            <p className="mt-3 text-[11px] text-slate-400">
              Key confidence {Math.round(analysis.key.confidence * 100)}% · analysed in{' '}
              {analysis.analysisSeconds}s
            </p>
          </div>

          <Tuner />
        </aside>
      </div>

      <ChordSheet
        title={song.title}
        artist={song.artist}
        analysis={analysis}
        transpose={settings.transpose}
        capo={settings.capo}
      />
    </div>
  )
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 px-4">
      {children}
    </div>
  )
}
