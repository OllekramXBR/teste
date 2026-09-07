import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { AudioEngine, voiceChord } from '../lib/audioEngine'
import { ChordPopover } from '../components/ChordPopover'
import { FretDiagram } from '../components/FretDiagram'
import { PianoDiagram } from '../components/PianoDiagram'
import { br } from '../lib/brazilian'
import { INSTRUMENTS, type Instrument } from '../lib/fretboard'
import {
  ALL_KEYS,
  chordPitchClasses,
  formatChord,
  mod12,
  noteName,
  QUALITIES,
  QUALITY_LABELS,
} from '../lib/theory'
import { Page, PageHeader } from '../components/Page'

type Mode = 'major' | 'minor'
type Func = 'T' | 'SD' | 'D'

interface Degree {
  /** Semitones above the tonic. */
  step: number
  triad: string
  seventh: string
  numeral: string
  func: Func
}

/** The seven degrees of the major key, with the sevenths a songbook uses. */
const MAJOR_DEGREES: Degree[] = [
  { step: 0, triad: '', seventh: 'maj7', numeral: 'I', func: 'T' },
  { step: 2, triad: 'm', seventh: 'm7', numeral: 'ii', func: 'SD' },
  { step: 4, triad: 'm', seventh: 'm7', numeral: 'iii', func: 'T' },
  { step: 5, triad: '', seventh: 'maj7', numeral: 'IV', func: 'SD' },
  { step: 7, triad: '', seventh: '7', numeral: 'V', func: 'D' },
  { step: 9, triad: 'm', seventh: 'm7', numeral: 'vi', func: 'T' },
  { step: 11, triad: 'dim', seventh: 'm7b5', numeral: 'vii°', func: 'D' },
]

/** Natural minor. The raised dominant lives in the "temperos" list instead. */
const MINOR_DEGREES: Degree[] = [
  { step: 0, triad: 'm', seventh: 'm7', numeral: 'i', func: 'T' },
  { step: 2, triad: 'dim', seventh: 'm7b5', numeral: 'ii°', func: 'SD' },
  { step: 3, triad: '', seventh: 'maj7', numeral: 'III', func: 'T' },
  { step: 5, triad: 'm', seventh: 'm7', numeral: 'iv', func: 'SD' },
  { step: 7, triad: 'm', seventh: 'm7', numeral: 'v', func: 'D' },
  { step: 8, triad: '', seventh: 'maj7', numeral: 'VI', func: 'T' },
  { step: 10, triad: '', seventh: '7', numeral: 'VII', func: 'D' },
]

const FUNC_LABEL: Record<Func, string> = {
  T: 'tônica · repouso',
  SD: 'subdominante · caminho',
  D: 'dominante · tensão',
}

const FUNC_CLASS: Record<Func, string> = {
  T: 'bg-accent-soft text-accent-ink',
  SD: 'bg-flame-soft text-ink',
  D: 'bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300',
}

interface Progression {
  name: string
  hint: string
  degrees: number[]
}

/** Indexes into the degree table, so they resolve in any key. */
const MAJOR_PROGRESSIONS: Progression[] = [
  { name: 'I – V – vi – IV', hint: 'o pop inteiro', degrees: [0, 4, 5, 3] },
  { name: 'I – vi – IV – V', hint: 'anos 50, serestas', degrees: [0, 5, 3, 4] },
  { name: 'ii – V – I', hint: 'bossa e jazz, resolve', degrees: [1, 4, 0] },
  { name: 'I – IV – V – I', hint: 'raiz: rock, forró', degrees: [0, 3, 4, 0] },
  { name: 'vi – IV – I – V', hint: 'balada emotiva', degrees: [5, 3, 0, 4] },
]

const MINOR_PROGRESSIONS: Progression[] = [
  { name: 'i – VI – III – VII', hint: 'épica moderna', degrees: [0, 5, 2, 6] },
  { name: 'i – iv – v – i', hint: 'menor raiz', degrees: [0, 3, 4, 0] },
  { name: 'i – VII – VI – VII', hint: 'roda no escuro', degrees: [0, 6, 5, 6] },
]

interface Spice {
  label: (tonic: number, useFlats: boolean) => string
  numeral: string
  hint: string
}

/** The borrowings a songbook actually meets, one line of why each. */
const MAJOR_SPICES: Spice[] = [
  {
    numeral: 'iv',
    label: (tonic, flats) => formatChord(mod12(tonic + 5), 'm', flats),
    hint: 'empréstimo do tom menor — a saudade no meio da alegria',
  },
  {
    numeral: 'bVII',
    label: (tonic, flats) => formatChord(mod12(tonic + 10), '', flats),
    hint: 'mixolídio — o rock e o baião moram aqui',
  },
  {
    numeral: 'V/V',
    label: (tonic, flats) => formatChord(mod12(tonic + 2), '7', flats),
    hint: 'dominante secundária — prepara o V como se fosse um tom novo',
  },
  {
    numeral: 'V/vi',
    label: (tonic, flats) => formatChord(mod12(tonic + 4), '7', flats),
    hint: 'prepara o vi — a porta para o relativo menor',
  },
]

const MINOR_SPICES: Spice[] = [
  {
    numeral: 'V7',
    label: (tonic, flats) => formatChord(mod12(tonic + 7), '7', flats),
    hint: 'menor harmônica — a tensão que o v natural não tem',
  },
  {
    numeral: 'IV',
    label: (tonic, flats) => formatChord(mod12(tonic + 5), '', flats),
    hint: 'dórico — o menor que sorri',
  },
  {
    numeral: 'bII',
    label: (tonic, flats) => formatChord(mod12(tonic + 1), '', flats),
    hint: 'napolitano — drama de novela, resolve no V',
  },
]

const INSTRUMENT_KEY = 'metatron.chordInstrument.v1'
type DiagramInstrument = Instrument['id'] | 'piano'

const DIAGRAM_CHOICES: { id: DiagramInstrument; label: string }[] = [
  { id: 'guitar', label: 'Violão' },
  { id: 'piano', label: 'Teclado' },
  { id: 'cavaquinho', label: 'Cavaquinho' },
  { id: 'ukulele', label: 'Ukulele' },
]

/**
 * The chord dictionary, taught instead of listed.
 *
 * Chords only mean something in a key: pick one and this page lays out its
 * harmonic field — the seven degrees with their function (rest, path,
 * tension), the progressions those functions form, and the borrowed chords a
 * real songbook sneaks in. Every chord is playable on tap, so the page
 * answers "what does ii–V–I feel like" with sound rather than prose. The old
 * exhaustive table survives at the bottom for the reader who just needs a
 * shape.
 */
export function DictionaryPage() {
  // A song page can send its own key here: /dicionario?tom=7&modo=minor
  const [params] = useSearchParams()
  const [tonic, setTonic] = useState(() => {
    const raw = params.get('tom')
    // Number(null) is 0, which would silently turn "no param" into C.
    const fromUrl = raw === null ? NaN : Number(raw)
    return Number.isInteger(fromUrl) && fromUrl >= 0 && fromUrl < 12 ? fromUrl : 7
  })
  const [mode, setMode] = useState<Mode>(() =>
    params.get('modo') === 'minor' ? 'minor' : 'major',
  )
  const [useFlats, setUseFlats] = useState(false)
  const [withSevenths, setWithSevenths] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [instrument, setInstrument] = useState<DiagramInstrument>(
    () => (localStorage.getItem(INSTRUMENT_KEY) as DiagramInstrument) || 'guitar',
  )
  const [playingStep, setPlayingStep] = useState<number | null>(null)

  const engineRef = useRef<AudioEngine | null>(null)
  if (engineRef.current === null) engineRef.current = new AudioEngine()
  const engine = engineRef.current
  const timeoutsRef = useRef<number[]>([])

  useEffect(() => {
    localStorage.setItem(INSTRUMENT_KEY, instrument)
  }, [instrument])

  useEffect(
    () => () => {
      timeoutsRef.current.forEach((timeout) => window.clearTimeout(timeout))
      engine.dispose()
    },
    [engine],
  )

  const degrees = mode === 'major' ? MAJOR_DEGREES : MINOR_DEGREES
  const progressions = mode === 'major' ? MAJOR_PROGRESSIONS : MINOR_PROGRESSIONS
  const spices = mode === 'major' ? MAJOR_SPICES : MINOR_SPICES

  const chords = useMemo(
    () =>
      degrees.map((degree) => {
        const root = mod12(tonic + degree.step)
        const quality = withSevenths ? degree.seventh : degree.triad
        return { ...degree, root, quality, label: formatChord(root, quality, useFlats) }
      }),
    [degrees, tonic, withSevenths, useFlats],
  )

  const relative = useMemo(() => {
    if (mode === 'major') {
      return { tonic: mod12(tonic + 9), mode: 'minor' as Mode, label: 'relativo menor' }
    }
    return { tonic: mod12(tonic + 3), mode: 'major' as Mode, label: 'relativo maior' }
  }, [tonic, mode])

  /** Sound one chord now; the ear is the whole point of this page. */
  const playChordNow = (root: number, quality: string) => {
    void engine.resume().then(() => {
      engine.setChordVolume(0.9)
      engine.playChord(
        voiceChord(root, chordPitchClasses(root, quality)),
        engine.currentTime + 0.05,
        'guitar',
        1.1,
      )
    })
  }

  /** Sound a progression, lighting each degree card as it lands. */
  const playProgression = (progression: Progression) => {
    timeoutsRef.current.forEach((timeout) => window.clearTimeout(timeout))
    timeoutsRef.current = []
    void engine.resume().then(() => {
      engine.setChordVolume(0.9)
      const start = engine.currentTime + 0.08
      progression.degrees.forEach((degreeIndex, position) => {
        const chord = chords[degreeIndex]
        engine.playChord(
          voiceChord(chord.root, chordPitchClasses(chord.root, chord.quality)),
          start + position * 0.95,
          'guitar',
          1.05,
        )
        timeoutsRef.current.push(
          window.setTimeout(() => setPlayingStep(degreeIndex), position * 950 + 80),
        )
      })
      timeoutsRef.current.push(
        window.setTimeout(() => setPlayingStep(null), progression.degrees.length * 950 + 200),
      )
    })
  }

  const qualities = useMemo(() => Object.keys(QUALITIES), [])

  return (
    <Page width="wide">
      <PageHeader
        title="Campos harmônicos"
        description="Escolha um tom e veja a família dele: os sete graus, a função de cada um e as progressões que eles formam. Toque em qualquer acorde para ouvir e ver a digitação."
      />

      {/* The key picker: one row of tonics, one mode switch. */}
      <div className="glass animate-fade-up flex flex-wrap items-center gap-3 rounded-2xl p-3">
        <div className="flex flex-wrap items-center gap-1">
          {ALL_KEYS.map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setTonic(key)}
              className={`h-9 w-9 rounded-full text-sm font-bold transition-all ${
                key === tonic
                  ? 'bg-accent text-canvas shadow-[0_0_12px_color-mix(in_oklab,var(--color-accent)_45%,transparent)]'
                  : 'text-ink-soft hover:bg-accent-soft hover:text-ink'
              }`}
            >
              {noteName(key, useFlats)}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 rounded-full bg-canvas/60 p-1">
          {(['major', 'minor'] as Mode[]).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setMode(option)}
              className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                mode === option ? 'bg-accent text-canvas' : 'text-ink-soft hover:text-ink'
              }`}
            >
              {option === 'major' ? 'maior' : 'menor'}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button
            type="button"
            onClick={() => setUseFlats((previous) => !previous)}
            className="rounded-full border border-line px-3 py-1 font-medium text-ink-soft transition hover:border-accent hover:text-accent"
          >
            {useFlats ? 'bemóis' : 'sustenidos'}
          </button>
          <button
            type="button"
            onClick={() => setWithSevenths((previous) => !previous)}
            aria-pressed={withSevenths}
            className={`rounded-full border px-3 py-1 font-medium transition ${
              withSevenths
                ? 'border-accent bg-accent-soft text-accent-ink'
                : 'border-line text-ink-soft hover:border-accent hover:text-accent'
            }`}
          >
            com sétimas
          </button>
          <select
            value={instrument}
            onChange={(event) => setInstrument(event.target.value as DiagramInstrument)}
            className="rounded-full border border-line bg-panel px-3 py-1 text-xs"
          >
            {DIAGRAM_CHOICES.map((choice) => (
              <option key={choice.id} value={choice.id}>
                {choice.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => {
              setTonic(relative.tonic)
              setMode(relative.mode)
            }}
            className="rounded-full border border-line px-3 py-1 font-medium text-ink-soft transition hover:border-flame hover:text-flame"
            title="O tom irmão, com os mesmos acordes"
          >
            {relative.label}: {noteName(relative.tonic, useFlats)}
            {relative.mode === 'minor' ? 'm' : ''} →
          </button>
        </div>
      </div>

      {/* The seven degrees. This row IS the harmonic field. */}
      <div className="animate-fade-up grid grid-cols-2 gap-3 [animation-delay:.08s] sm:grid-cols-4 lg:grid-cols-7">
        {chords.map((chord, index) => (
          <button
            key={chord.numeral}
            type="button"
            onClick={() => {
              playChordNow(chord.root, chord.quality)
              setSelected(chord.label)
            }}
            className={`glass group flex flex-col items-center gap-1.5 rounded-2xl p-3 text-center transition-all hover:-translate-y-0.5 ${
              playingStep === index
                ? 'ring-2 ring-accent shadow-[0_0_18px_color-mix(in_oklab,var(--color-accent)_45%,transparent)]'
                : ''
            }`}
            title="Tocar e ver a digitação"
          >
            <span className="text-xs font-bold tracking-widest text-ink-faint">
              {chord.numeral}
            </span>
            <span className="text-2xl font-extrabold tracking-tight text-ink group-hover:text-accent">
              {br(chord.label, useFlats)}
            </span>
            {instrument === 'piano' ? (
              <PianoDiagram
                root={chord.root}
                notes={chordPitchClasses(chord.root, chord.quality).map(mod12)}
                useFlats={useFlats}
                width={120}
              />
            ) : (
              <FretDiagram
                root={chord.root}
                quality={chord.quality}
                instrument={INSTRUMENTS[instrument] ?? INSTRUMENTS.guitar}
                useFlats={useFlats}
                width={104}
              />
            )}
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${FUNC_CLASS[chord.func]}`}
            >
              {FUNC_LABEL[chord.func]}
            </span>
          </button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Progressions: the field in motion. */}
        <section className="glass animate-fade-up rounded-2xl p-4 [animation-delay:.14s]">
          <h2 className="mb-1 text-sm font-bold">Progressões para treinar</h2>
          <p className="mb-3 text-xs text-ink-soft">
            Aperte o play e olhe os cartões acenderem na ordem. Depois toque junto.
          </p>
          <ul className="space-y-2">
            {progressions.map((progression) => (
              <li key={progression.name} className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => playProgression(progression)}
                  aria-label={`Tocar ${progression.name}`}
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-canvas transition active:scale-95"
                  style={{
                    background:
                      'linear-gradient(135deg, var(--color-accent), var(--color-flame))',
                  }}
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                    <path d="M2 1v10l9-5z" />
                  </svg>
                </button>
                <div className="min-w-0">
                  <p className="text-sm font-semibold">
                    {progression.degrees
                      .map((index) => br(chords[index].label, useFlats))
                      .join(' – ')}
                  </p>
                  <p className="text-[11px] text-ink-faint">
                    {progression.name} · {progression.hint}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </section>

        {/* Borrowed chords: what a real songbook adds to the field. */}
        <section className="glass animate-fade-up rounded-2xl p-4 [animation-delay:.2s]">
          <h2 className="mb-1 text-sm font-bold">Temperos fora do campo</h2>
          <p className="mb-3 text-xs text-ink-soft">
            Os acordes que as músicas emprestam de outros tons — e por que caem tão bem.
          </p>
          <ul className="space-y-2">
            {spices.map((spice) => {
              const label = spice.label(tonic, useFlats)
              return (
                <li key={spice.numeral} className="flex items-start gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      const parsed = label.match(/^([A-G][#b]?)(.*)$/)
                      const rootName = parsed?.[1] ?? label
                      const rootIndex = ALL_KEYS.find(
                        (key) =>
                          noteName(key, false) === rootName || noteName(key, true) === rootName,
                      )
                      if (rootIndex !== undefined) playChordNow(rootIndex, parsed?.[2] ?? '')
                      setSelected(label)
                    }}
                    className="w-16 shrink-0 rounded-lg bg-canvas px-2 py-1.5 text-sm font-bold transition hover:bg-accent-soft hover:text-accent-ink"
                  >
                    {br(label, useFlats)}
                  </button>
                  <div className="min-w-0 pt-0.5">
                    <p className="text-xs font-semibold text-ink-soft">{spice.numeral}</p>
                    <p className="text-[11px] leading-snug text-ink-faint">{spice.hint}</p>
                  </div>
                </li>
              )
            })}
          </ul>
        </section>
      </div>

      {/* The exhaustive table, demoted to an appendix but intact. */}
      <details className="glass animate-fade-up rounded-2xl p-4 [animation-delay:.26s]">
        <summary className="cursor-pointer list-none text-sm font-bold marker:content-none">
          Todos os acordes
          <span className="float-right text-xs font-normal text-ink-faint">
            {ALL_KEYS.length * qualities.length} formas · tabela completa
          </span>
        </summary>
        <div className="mt-4 space-y-5">
          {qualities.map((option) => (
            <section key={option}>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">
                {QUALITY_LABELS[option] ?? (option || 'maior')}
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {ALL_KEYS.map((root) => {
                  const label = formatChord(root, option, useFlats)
                  return (
                    <button
                      key={`${root}-${option}`}
                      type="button"
                      onClick={() => setSelected(label)}
                      className="rounded-lg border border-line bg-panel px-3 py-2 text-sm font-semibold transition hover:border-accent hover:text-accent"
                    >
                      {br(label, useFlats)}
                    </button>
                  )
                })}
              </div>
            </section>
          ))}
          <p className="text-[11px] text-ink-faint">
            As formas são procuradas no braço de cada instrumento, não tiradas de uma tabela — por
            isso cavaquinho e viola caipira funcionam igual ao violão.
          </p>
        </div>
      </details>

      {selected && (
        <ChordPopover label={selected} useFlats={useFlats} onClose={() => setSelected(null)} />
      )}
    </Page>
  )
}

/** Roots as note names, for anything that wants to label an axis. */
export const ROOT_NAMES = (useFlats: boolean) => ALL_KEYS.map((root) => noteName(root, useFlats))
