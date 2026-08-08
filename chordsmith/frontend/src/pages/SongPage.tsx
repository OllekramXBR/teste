import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import * as api from '../lib/api'
import type { Analysis, Song } from '../lib/api'
import { AudioEngine, voiceChord, type InstrumentVoice } from '../lib/audioEngine'
import { keyNamePt, mod12, parseLabel, romanNumeral } from '../lib/theory'
import { usePlayer } from '../hooks/usePlayer'
import { br } from '../lib/brazilian'
import { buildChordCards, ChordFilmstrip } from '../components/ChordFilmstrip'
import { ChordGrid, displayLabel, groupIntoBars } from '../components/ChordGrid'
import { ChordPopover } from '../components/ChordPopover'
import { ChordSheet } from '../components/ChordSheet'
import { KaraokeView } from '../components/KaraokeView'
import { KeyChooser } from '../components/KeyChooser'
import { LyricEditor } from '../components/LyricEditor'
import { NowPlaying } from '../components/NowPlaying'
import { ProductionCard } from '../components/ProductionCard'
import { useJobProgress } from '../hooks/useJobProgress'
import { StaffNotation } from '../components/StaffNotation'
import { LeadSummary, TabStaff } from '../components/TabStaff'
import { Toolbar, type ToolbarSettings } from '../components/Toolbar'
import { Transport } from '../components/Transport'
import { Tuner } from '../components/Tuner'
import { WebChartPanel } from '../components/WebChartPanel'

type View = 'chords' | 'estudo' | 'tab' | 'letra' | 'cifra' | 'partitura' | 'both'

const VIEW_LABELS: Record<View, string> = {
  chords: 'Grade',
  estudo: 'Estudo',
  tab: 'Tablatura',
  letra: 'Letra',
  cifra: 'Cifra',
  partitura: 'Partitura',
  both: 'Tudo',
}

const SETTINGS_KEY = 'chordsmith.settings.v1'

/** Which of the synth's three voices stands in for each fretboard instrument. */
const SYNTH_VOICES: Record<string, InstrumentVoice> = {
  guitar: 'guitar',
  piano: 'piano',
  ukulele: 'ukulele',
  cavaquinho: 'ukulele',
  mandolin: 'ukulele',
  banjo: 'ukulele',
  viola: 'guitar',
  bass: 'guitar',
}
const POLL_INTERVAL_MS = 1500
const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

const DEFAULT_SETTINGS: ToolbarSettings = {
  transpose: 0,
  capo: 0,
  rate: 1,
  songVolume: 0.85,
  chordVolume: 0,
  clickVolume: 0,
  instrument: 'guitar',
  autoScroll: true,
  simplify: true,
  countIn: 0,
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
  const [stems, setStems] = useState<api.Stem[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [cifra, setCifra] = useState('')
  const [editingLyrics, setEditingLyrics] = useState(false)
  const [popoverChord, setPopoverChord] = useState<string | null>(null)
  const [countdown, setCountdown] = useState(0)
  const [tracks, setTracks] = useState<{
    status: 'none' | 'pending' | 'ready'
    tracks: api.TranscribedTrack[]
  }>({ status: 'none', tracks: [] })
  const [renderedKeys, setRenderedKeys] = useState<Set<number>>(new Set())

  const engineRef = useRef<AudioEngine | null>(null)
  if (engineRef.current === null) engineRef.current = new AudioEngine()
  const engine = engineRef.current

  const analysis = song?.analysis ?? null
  // Only while something is actually running, so an idle page is silent.
  const jobsRunning = Boolean(
    song &&
      ['pending', 'analyzing', 'transcribing', 'separating'].some((state) =>
        [song.status, song.lyricsStatus, song.stemsStatus].includes(state as typeof song.status),
      ),
  )
  const progress = useJobProgress(songId, jobsRunning)
  const audioUrl = song ? song.audioUrl : null
  const player = usePlayer(audioUrl)

  // Refs the scheduler reads; it runs on a timer, outside the render cycle.
  const settingsRef = useRef(settings)
  settingsRef.current = settings
  const analysisRef = useRef(analysis)
  analysisRef.current = analysis
  // Space bar reaches the current handler without the listener depending on it.
  const toggleRef = useRef<() => void>(() => {})

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    const poll = async () => {
      try {
        const fetched = await api.getSong(songId)
        if (cancelled) return
        setSong(fetched)
        setLoadError(null)
        // Transcription and separation are minutes long, so the same poll that
        // waits for the analysis keeps watching them; without it a job that
        // finishes while the tab sits open never shows up.
        const running = [fetched.status, fetched.lyricsStatus, fetched.stemsStatus].some((status) =>
          ['pending', 'analyzing', 'transcribing', 'separating'].includes(status),
        )
        if (running) timer = window.setTimeout(poll, POLL_INTERVAL_MS)
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

  // One deduplicated sequence of chord cards, shared by the now-playing panel
  // and the filmstrip so both agree on what "the current chord" is.
  const chordCards = useMemo(
    () =>
      analysis
        ? buildChordCards(
            analysis.chords,
            settings.transpose,
            settings.capo,
            analysis.useFlats,
            settings.simplify,
          )
        : [],
    [analysis, settings.transpose, settings.capo, settings.simplify],
  )

  /**
   * The tablature, taken from the separated guitar stem when one exists.
   *
   * The old source was the whole mix, and a pitch tracker pointed at a mix
   * follows the highest melodic voice — on a sung recording that is the singer,
   * not the guitar. The tab was therefore often a transcription of the vocal
   * line printed on six strings, which is exactly as useful as it sounds.
   */
  const guitarLead = useMemo(() => {
    if (tracks.status !== 'ready' || !analysis) return null
    const guitar = tracks.tracks.find((track) => track.stem === 'other')
    if (!guitar?.notes.length) return null

    const times = analysis.beats.map((beat) => beat.time)
    const beatAt = (time: number) => {
      let low = 0
      let high = times.length - 1
      let found = 0
      while (low <= high) {
        const middle = (low + high) >> 1
        if (times[middle] <= time) {
          found = middle
          low = middle + 1
        } else high = middle - 1
      }
      return found
    }

    return {
      ...analysis.lead,
      notes: guitar.notes.map((note) => {
        const beat = beatAt(note.start)
        return {
          start: note.start,
          end: note.end,
          midi: note.midi,
          name: NOTE_NAMES[((note.midi % 12) + 12) % 12] + (Math.floor(note.midi / 12) - 1),
          string: note.string ?? null,
          fret: note.fret ?? null,
          beat,
          bar: analysis.beats[beat]?.bar ?? 1,
          confidence: 1,
          velocity: note.velocity,
        }
      }),
      // Solo detection was computed over the mix and describes a different
      // signal, so it is dropped rather than shown against these notes.
      sections: [],
    }
  }, [tracks, analysis])

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
      // The synth has three voices; the fretboard now knows eight instruments.
      // Anything plucked that is not the ukulele is played with the guitar
      // voice — a synthesised cavaquinho would be a lie either way, and the
      // point of this track is to hear the harmony, not the timbre.
      const voice = SYNTH_VOICES[active.instrument] ?? 'guitar'

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
        toggleRef.current()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const activeBeatIndex = findActiveBeat(analysis, player.currentTime)

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

  /**
   * Play, after counting the band in.
   *
   * The clicks are scheduled on the audio clock and the recording is started
   * against the same clock, rather than by a timer that fires whenever the
   * browser gets round to it. A count-in that lands a beat late is worse than
   * none: it teaches the wrong tempo for the length of one bar and then hands
   * over to a recording that disagrees.
   */
  const handleToggle = useCallback(() => {
    if (player.playing || countdown > 0) {
      player.pause()
      setCountdown(0)
      return
    }
    const bars = settings.countIn
    if (!bars || !analysis || !analysis.bpm) {
      void player.play()
      return
    }

    const secondsPerBeat = 60 / analysis.bpm
    const beats = bars * analysis.beatsPerBar

    void engine.resume().then(() => {
      const start = engine.currentTime + 0.12
      for (let beat = 0; beat < beats; beat += 1) {
        engine.playClick(start + beat * secondsPerBeat, beat % analysis.beatsPerBar === 0)
      }
      setCountdown(beats)
      for (let beat = 1; beat <= beats; beat += 1) {
        window.setTimeout(
          () => setCountdown(beats - beat),
          (start - engine.currentTime + beat * secondsPerBeat) * 1000,
        )
      }
      window.setTimeout(
        () => void player.play(),
        (start - engine.currentTime + beats * secondsPerBeat) * 1000,
      )
    })
  }, [player, countdown, settings.countIn, analysis, engine])

  toggleRef.current = handleToggle

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

  // Stems are files on disk rather than a column in the song row, so they are
  // asked for separately and refreshed whenever the job status changes.
  useEffect(() => {
    let cancelled = false
    api
      .getStems(songId)
      .then((response) => !cancelled && setStems(response.stems))
      .catch(() => !cancelled && setStems([]))
    return () => {
      cancelled = true
    }
  }, [songId, song?.stemsStatus])

  useEffect(() => {
    if (view !== 'cifra' || !song || song.status !== 'ready') return
    let cancelled = false
    api
      .getCifra(song.id, { transpose: settings.transpose, capo: settings.capo })
      .then((text) => !cancelled && setCifra(text))
      .catch(() => !cancelled && setCifra('Não consegui montar a cifra.'))
    return () => {
      cancelled = true
    }
  }, [view, song, settings.transpose, settings.capo])

  // The transcription is queued by the first request, so opening the view is
  // what starts it; polling stops as soon as it is ready.
  useEffect(() => {
    if (view !== 'partitura' || !song || song.status !== 'ready') return
    let cancelled = false
    let timer: number | undefined

    const poll = async () => {
      try {
        const response = await api.getTracks(song.id)
        if (cancelled) return
        setTracks(response)
        if (response.status === 'pending') timer = window.setTimeout(poll, 5000)
      } catch {
        if (!cancelled) setTracks({ status: 'none', tracks: [] })
      }
    }

    void poll()
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [view, song])

  const handleTranscribe = useCallback(async () => {
    if (!song) return
    setBusy('lyrics')
    try {
      setSong(await api.transcribeLyrics(song.id))
    } finally {
      setBusy(null)
    }
  }, [song])

  const handleSeparate = useCallback(async () => {
    if (!song) return
    setBusy('stems')
    try {
      setSong(await api.separateStems(song.id))
    } finally {
      setBusy(null)
    }
  }, [song])

  // Which keys already have audio rendered, so the chooser can say so instead
  // of offering to render the same thing twice.
  useEffect(() => {
    if (!song || !stems.length) return
    let cancelled = false
    api
      .listVariants(song.id)
      .then(({ variants }) => {
        if (cancelled) return
        const keys = new Set<number>()
        for (const variant of variants) {
          const match = variant.key.match(/^t([pm])(\d+)_r100$/)
          if (match) keys.add(match[1] === 'm' ? -Number(match[2]) : Number(match[2]))
        }
        setRenderedKeys(keys)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [song, stems.length, busy])

  const handleRenderAudio = useCallback(
    async (semitones: number) => {
      if (!song) return
      setBusy('variant')
      try {
        await api.renderVariant(song.id, semitones)
      } finally {
        setBusy(null)
      }
    },
    [song],
  )

  const handleSaveLyrics = useCallback(
    async (segments: api.LyricSegment[]) => {
      if (!song) return
      setBusy('edit')
      try {
        const { lyrics } = await api.editLyrics(song.id, segments)
        setSong({ ...song, lyrics })
        setEditingLyrics(false)
      } finally {
        setBusy(null)
      }
    },
    [song],
  )

  const handleReanalyze = useCallback(async () => {
    if (!song) return
    const updated = await api.reanalyze(song.id)
    setSong({ ...song, ...updated, analysis: null })
  }, [song])

  if (loadError) {
    return (
      <Centered>
        <p className="text-rose-500">{loadError}</p>
        <Link to="/" className="text-sm text-accent hover:underline">
          Voltar para a biblioteca
        </Link>
      </Centered>
    )
  }

  if (!song) return <Centered>Carregando…</Centered>

  if (song.status === 'failed') {
    return (
      <Centered>
        <h2 className="text-lg font-semibold">A análise falhou</h2>
        <p className="max-w-md text-center text-sm text-ink-soft">{song.error}</p>
        <button
          type="button"
          onClick={handleReanalyze}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-canvas transition hover:brightness-110"
        >
          Tentar de novo
        </button>
      </Centered>
    )
  }

  if (song.status !== 'ready' || !analysis) {
    return (
      <Centered>
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-line border-t-accent" />
        <h2 className="text-lg font-semibold">Detectando batidas e acordes…</h2>
        <p className="text-sm text-ink-soft">
          {song.title} — costuma levar poucos segundos por minuto de áudio.
        </p>
      </Centered>
    )
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5 px-4 py-6 print:px-0 print:py-0">
      <div className="animate-fade-up print:hidden">
        <Link to="/" className="text-xs text-ink-soft transition-colors hover:text-accent">
          ← Biblioteca
        </Link>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold">{song.title}</h1>
            <p className="text-sm text-ink-soft">
              {song.artist || 'Artista desconhecido'} ·{' '}
              {keyNamePt(analysis.key.tonic, analysis.key.mode, analysis.useFlats)} ·{' '}
              {Math.round(analysis.bpm)} BPM · {analysis.beatsPerBar}/4 ·{' '}
              {analysis.chords.length} trocas de acorde
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a
              href={api.midiUrl(song.id, settings.transpose)}
              className="rounded border border-line px-3 py-1.5 text-xs font-semibold transition-colors hover:border-accent hover:text-accent"
            >
              Baixar MIDI
            </a>
            <button
              type="button"
              onClick={() => window.print()}
              className="rounded border border-line px-3 py-1.5 text-xs font-semibold transition-colors hover:border-accent hover:text-accent"
            >
              Cifra em PDF
            </button>
            <button
              type="button"
              onClick={handleReanalyze}
              className="rounded border border-line px-3 py-1.5 text-xs font-semibold transition-colors hover:border-accent hover:text-accent"
            >
              Reanalisar
            </button>
            <button
              type="button"
              onClick={handleDelete}
              className="rounded border border-rose-300 px-3 py-1.5 text-xs font-semibold text-rose-600 transition-colors hover:bg-rose-50 dark:border-rose-700 dark:hover:bg-rose-950/40"
            >
              Apagar
            </button>
          </div>
        </div>
      </div>

      {player.error && (
        <p className="rounded bg-rose-100 p-2 text-sm text-rose-700 print:hidden dark:bg-rose-950/50 dark:text-rose-300">
          {player.error}
        </p>
      )}

      {countdown > 0 && (
        <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center bg-canvas/40 backdrop-blur-sm">
          <span
            key={countdown}
            className="text-neon animate-count-pulse rounded-3xl px-12 py-8 text-9xl font-extrabold tabular-nums"
          >
            {countdown}
          </span>
        </div>
      )}

      <div className="animate-fade-up [animation-delay:.06s] print:hidden">
        <Transport
          playing={player.playing}
          currentTime={player.currentTime}
          duration={player.duration || analysis.duration}
          beats={analysis.beats}
          loopRegion={loopRegion}
          onToggle={handleToggle}
          onSeek={handleSeek}
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_260px] print:hidden">
        <div className="min-w-0 space-y-4">
          <div className="animate-fade-up [animation-delay:.12s]">
          <Toolbar
            settings={settings}
            onChange={handleSettings}
            keyTonic={analysis.key.tonic}
            keyMode={analysis.key.mode}
            useFlats={analysis.useFlats}
            loopBars={loopBars}
            onClearLoop={() => setLoopBars(null)}
          />
          </div>
          {settings.transpose !== 0 && (
            <p className="rounded-lg border border-flame/30 bg-flame-soft px-3 py-2 text-xs text-ink">
              A grade está transposta {settings.transpose > 0 ? '+' : ''}
              {settings.transpose} semitons, mas a gravação continua em{' '}
              {keyNamePt(analysis.key.tonic, analysis.key.mode, analysis.useFlats)}. Abaixe o volume
              da música e suba o dos acordes para ouvir a harmonia transposta.
            </p>
          )}

          <div className="animate-fade-up [animation-delay:.18s]">
          <NowPlaying
            cards={chordCards}
            currentTime={player.currentTime}
            capo={settings.capo}
            instrument={settings.instrument}
            useFlats={analysis.useFlats}
            shapeVariant={shapeVariant}
            onCycleShape={() => setShapeVariant((previous) => (previous + 1) % 4)}
            onOpenPopover={setPopoverChord}
            onSeek={handleSeek}
          />
          </div>

          <div className="glass animate-fade-up flex items-center gap-1 overflow-x-auto rounded-full p-1 [animation-delay:.24s]">
            {(['chords', 'estudo', 'tab', 'letra', 'cifra', 'partitura', 'both'] as View[]).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setView(option)}
                className={`shrink-0 rounded-full px-3.5 py-1.5 text-xs font-semibold transition-all ${
                  view === option
                    ? 'bg-accent text-canvas shadow-[0_0_14px_color-mix(in_oklab,var(--color-accent)_45%,transparent)]'
                    : 'text-ink-soft hover:text-ink'
                }`}
              >
                {VIEW_LABELS[option]}
              </button>
            ))}
          </div>

          {(view === 'estudo' || view === 'both') && (
            <ChordFilmstrip
              chords={analysis.chords}
              transpose={settings.transpose}
              capo={settings.capo}
              useFlats={analysis.useFlats}
              simplify={settings.simplify}
              currentTime={player.currentTime}
              instrument={settings.instrument}
              onSeek={handleSeek}
            />
          )}

          {view === 'letra' && song.lyrics && editingLyrics && (
            <LyricEditor
              lyrics={song.lyrics}
              currentTime={player.currentTime}
              saving={busy === 'edit'}
              onSeek={handleSeek}
              onCancel={() => setEditingLyrics(false)}
              onSave={handleSaveLyrics}
            />
          )}

          {view === 'letra' &&
            !editingLyrics &&
            (song.lyrics ? (
              <div className="glass rounded-xl">
                <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5 ">
                  <span className="text-xs text-ink-soft">
                    {song.lyrics.wordCount} palavras
                    {song.lyrics.edited ? ' · corrigida à mão' : ` · ${song.lyrics.model}`}
                  </span>
                  <button
                    type="button"
                    onClick={() => setEditingLyrics(true)}
                    className="rounded-full border border-line px-3 py-1 text-xs font-medium transition hover:border-accent hover:text-accent "
                  >
                    Corrigir letra
                  </button>
                </div>
                <KaraokeView
                  lyrics={song.lyrics}
                  chords={analysis.chords
                    .filter((chord) => chord.root !== null)
                    .map((chord) => ({
                      label: br(
                        displayLabel(
                          chord.label,
                          settings.transpose,
                          settings.capo,
                          analysis.useFlats,
                          settings.simplify,
                        ),
                        analysis.useFlats,
                      ),
                      start: chord.start,
                    }))}
                  currentTime={player.currentTime}
                  onSeek={handleSeek}
                />
              </div>
            ) : (
              <p className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-ink-soft ">
                Ainda não transcrevi a letra desta música. O botão está no painel Produção.
              </p>
            ))}

          {view === 'partitura' && (
            <div className="space-y-4">
              {tracks.status === 'none' && (
                <p className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-ink-soft ">
                  A partitura vem das pistas separadas. Separe esta música primeiro.
                </p>
              )}
              {tracks.status === 'pending' && (
                <p className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-ink-soft ">
                  Transcrevendo cada pista. Leva cerca de um minuto — a página atualiza sozinha.
                </p>
              )}
              {tracks.status === 'ready' && (
                <>
                  <div className="flex justify-end">
                    <a
                      href={api.midiMultitrackUrl(song.id, settings.transpose)}
                      className="rounded-full border border-line px-3 py-1 text-xs font-medium transition hover:border-accent hover:text-accent "
                    >
                      Baixar MIDI multipista
                    </a>
                  </div>
                  {tracks.tracks.map((track) => (
                    <section
                      key={track.name}
                      className="glass rounded-xl p-4"
                    >
                      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">
                        {track.name} · {track.notes.length} notas
                      </h3>
                      <StaffNotation
                        track={track}
                        bpm={analysis.bpm}
                        beatsPerBar={analysis.beatsPerBar}
                        currentTime={player.currentTime}
                        onSeek={handleSeek}
                      />
                    </section>
                  ))}
                </>
              )}
            </div>
          )}

          {view === 'cifra' && (
            <div className="space-y-4">
              <WebChartPanel songId={song.id} />
              <div className="glass rounded-xl p-5">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold">Cifra da análise</h3>
                  <a
                    href={api.cifraUrl(song.id, {
                      transpose: settings.transpose,
                      capo: settings.capo,
                      download: true,
                    })}
                    className="rounded-full border border-line px-3 py-1 text-xs font-medium transition hover:border-accent hover:text-accent "
                  >
                    Baixar .txt
                  </a>
                </div>
                <pre className="overflow-x-auto whitespace-pre font-mono text-[13px] leading-6">
                  {cifra || 'Montando…'}
                </pre>
              </div>
            </div>
          )}

          {(view === 'chords' || view === 'both') && (
            <ChordGrid
              beats={analysis.beats}
              beatsPerBar={analysis.beatsPerBar}
              activeBeat={activeBeatIndex}
              transpose={settings.transpose}
              capo={settings.capo}
              useFlats={analysis.useFlats}
              simplify={settings.simplify}
              loopBars={loopBars}
              onSeek={handleSeek}
              onBarSelect={handleBarSelect}
              autoScroll={settings.autoScroll && view !== 'both'}
            />
          )}

          {(view === 'tab' || view === 'both') && (
            <>
              <p
                className={[
                  'rounded-lg px-3 py-2 text-xs',
                  guitarLead
                    ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300'
                    : 'bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200',
                ].join(' ')}
              >
                {guitarLead
                  ? 'Transcrita da pista de guitarra separada — sem a voz no caminho.'
                  : 'Transcrita da mistura inteira, então ela segue a voz melódica mais aguda — que numa música cantada costuma ser o vocal, não o violão. Separe as pistas para transcrever a guitarra de verdade.'}
              </p>
              <LeadSummary lead={guitarLead ?? analysis.lead} onSeek={handleSeek} />
              <TabStaff
                lead={guitarLead ?? analysis.lead}
                bars={bars}
                currentTime={player.currentTime}
                onSeek={handleSeek}
                autoScroll={settings.autoScroll}
              />
            </>
          )}
        </div>

        <aside className="animate-fade-up space-y-4 [animation-delay:.2s]">
          <ProductionCard
            progress={progress}
            song={song}
            stems={stems}
            busy={busy}
            onTranscribe={handleTranscribe}
            onSeparate={handleSeparate}
          />

          <details className="glass group rounded-xl p-4">
            <summary className="cursor-pointer list-none text-sm font-semibold marker:content-none">
              Acordes desta música
              <span className="float-right text-xs font-normal text-ink-faint group-open:hidden">
                {analysis.uniqueChords.length}
              </span>
            </summary>
            <div className="mt-3">
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
                  <button
                    type="button"
                    key={label}
                    onClick={() => setPopoverChord(shown)}
                    title={numeral ? `${numeral} no tom` : 'fora do tom'}
                    className="rounded bg-canvas px-2 py-1 text-xs font-semibold transition hover:bg-accent-soft "
                  >
                    {br(shown, analysis.useFlats)}
                    {numeral && <span className="ml-1 text-[9px] text-ink-faint">{numeral}</span>}
                  </button>
                )
              })}
            </div>
              <p className="mt-3 text-[11px] text-ink-faint">
                Confiança do tom {Math.round(analysis.key.confidence * 100)}% · analisada em{' '}
                {analysis.analysisSeconds}s
              </p>
            </div>
          </details>

          {/* Deliberately collapsed: choosing a key is something done once per
              song, before playing — not something to stare at while singing.
              The chord panels above are what the session actually reads. */}
          <details className="glass rounded-xl p-4">
            <summary className="cursor-pointer list-none text-sm font-semibold marker:content-none">
              Em que tom cantar
              <span className="float-right text-xs font-normal text-ink-faint">
                {settings.transpose > 0 ? `+${settings.transpose}` : settings.transpose || ''}
              </span>
            </summary>
            <div className="mt-3">
              <KeyChooser
                frameless
                uniqueChords={analysis.uniqueChords}
                keyTonic={analysis.key.tonic}
                keyMode={analysis.key.mode}
                useFlats={analysis.useFlats}
                instrument={settings.instrument === 'piano' ? 'guitar' : settings.instrument}
                transpose={settings.transpose}
                onTranspose={(semitones) => handleSettings({ transpose: semitones })}
                onRenderAudio={stems.length ? handleRenderAudio : undefined}
                renderedKeys={renderedKeys}
              />
            </div>
          </details>

          <details className="glass rounded-xl p-4">
            <summary className="cursor-pointer list-none text-sm font-semibold marker:content-none">
              Afinador
            </summary>
            <div className="mt-3">
              <Tuner />
            </div>
          </details>
        </aside>
      </div>

      {popoverChord && (
        <ChordPopover
          label={popoverChord}
          useFlats={analysis.useFlats}
          onClose={() => setPopoverChord(null)}
        />
      )}

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
