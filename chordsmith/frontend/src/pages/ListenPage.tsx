import { useEffect, useMemo, useState } from 'react'

import { ChordPopover } from '../components/ChordPopover'
import { FretDiagram } from '../components/FretDiagram'
import { useChordListener } from '../hooks/useChordListener'
import { br } from '../lib/brazilian'
import { INSTRUMENTS, type Instrument } from '../lib/fretboard'
import { formatChord, noteName, QUALITY_LABELS } from '../lib/theory'

type Mode = 'detect' | 'practice'

/** What a beginner is actually drilling; the rest of the vocabulary can wait. */
const DRILL: { root: number; quality: string }[] = [
  { root: 0, quality: '' },
  { root: 2, quality: 'm' },
  { root: 4, quality: 'm' },
  { root: 5, quality: '' },
  { root: 7, quality: '' },
  { root: 9, quality: 'm' },
  { root: 2, quality: '' },
  { root: 9, quality: '' },
  { root: 4, quality: '' },
  { root: 7, quality: '7' },
]

// Held this long before a drill counts it, so brushing the right notes on the
// way to somewhere else does not score.
const HOLD_FRAMES = 20

export function ListenPage() {
  const { listening, error, heard, start, stop } = useChordListener()
  const [mode, setMode] = useState<Mode>('detect')
  const [instrument, setInstrument] = useState<Instrument['id']>('guitar')
  const [popover, setPopover] = useState<string | null>(null)

  const [target, setTarget] = useState(() => DRILL[0])
  const [held, setHeld] = useState(0)
  const [score, setScore] = useState({ right: 0, tries: 0 })

  const label = heard.root === null ? null : formatChord(heard.root, heard.quality)

  const matches =
    mode === 'practice' && heard.root === target.root && heard.quality === target.quality

  useEffect(() => {
    if (mode !== 'practice' || !listening) return
    if (!matches) {
      setHeld(0)
      return
    }
    setHeld((previous) => previous + 1)
  }, [matches, mode, listening, heard])

  useEffect(() => {
    if (held < HOLD_FRAMES) return
    setScore((previous) => ({ right: previous.right + 1, tries: previous.tries + 1 }))
    setHeld(0)
    setTarget(DRILL[Math.floor(Math.random() * DRILL.length)])
  }, [held])

  const targetLabel = useMemo(
    () => br(formatChord(target.root, target.quality)),
    [target],
  )

  return (
    <div className="mx-auto max-w-2xl space-y-6 px-4 py-8">
      <header>
        <h1 className="text-[26px] font-semibold tracking-tight">Ouvir</h1>
        <p className="mt-1 text-sm text-slate-500">
          Toque no seu instrumento e o Metatron diz qual acorde é. Nada sai daqui — o áudio é
          analisado no navegador e não chega a ser enviado a lugar nenhum.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1 rounded-lg bg-slate-200/70 p-1 dark:bg-slate-800">
          {(['detect', 'practice'] as Mode[]).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setMode(option)}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                mode === option
                  ? 'bg-panel text-slate-900 shadow-sm dark:text-white'
                  : 'text-slate-500'
              }`}
            >
              {option === 'detect' ? 'Que acorde é este' : 'Praticar'}
            </button>
          ))}
        </div>

        <select
          value={instrument}
          onChange={(event) => setInstrument(event.target.value as Instrument['id'])}
          className="rounded-lg border border-slate-300 bg-panel px-3 py-1.5 text-xs dark:border-slate-700"
        >
          {Object.values(INSTRUMENTS).map((option) => (
            <option key={option.id} value={option.id}>
              {option.name}
            </option>
          ))}
        </select>

        <button
          type="button"
          onClick={() => (listening ? stop() : void start())}
          className={`rounded-lg px-4 py-2 text-sm font-semibold ${
            listening
              ? 'bg-rose-500 text-white'
              : 'bg-slate-900 text-white dark:bg-white dark:text-slate-900'
          }`}
        >
          {listening ? 'Parar' : 'Ouvir'}
        </button>
      </div>

      {error && <p className="text-sm text-rose-500">{error}</p>}

      <section className="rounded-xl border border-slate-200 bg-panel p-6 dark:border-slate-800">
        {mode === 'practice' && (
          <div className="mb-5 text-center">
            <p className="text-xs uppercase tracking-wide text-slate-400">Toque este</p>
            <button
              type="button"
              onClick={() => setPopover(targetLabel)}
              className="text-4xl font-bold tracking-tight"
            >
              {targetLabel}
            </button>
            <p className="mt-1 text-xs text-slate-500">
              {score.right} {score.right === 1 ? 'acerto' : 'acertos'}
            </p>
            <div className="mx-auto mt-3 h-1 w-40 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
              <div
                className="h-full bg-emerald-500 transition-all"
                style={{ width: `${Math.min(100, (held / HOLD_FRAMES) * 100)}%` }}
              />
            </div>
          </div>
        )}

        <div className="text-center">
          <p
            className={`text-5xl font-bold tracking-tight ${
              matches ? 'text-emerald-500' : label ? 'text-accent' : 'text-slate-300 dark:text-slate-700'
            }`}
          >
            {label ? br(label) : listening ? '…' : '—'}
          </p>
          <p className="mt-1 h-4 text-xs text-slate-500">
            {label && heard.quality in QUALITY_LABELS ? QUALITY_LABELS[heard.quality] : ''}
          </p>
        </div>

        {heard.root !== null && (
          <div className="mt-5 flex justify-center">
            <FretDiagram
              root={heard.root}
              quality={heard.quality}
              instrument={INSTRUMENTS[instrument]}
              useFlats={false}
              variant={0}
              width={150}
            />
          </div>
        )}

        {/* What the microphone actually hears, so a wrong answer is explainable
            rather than mysterious: a bright bar on a note you did not play is
            usually a string ringing that should have been muted. */}
        <div className="mt-6 flex items-end justify-center gap-1" aria-hidden="true">
          {heard.chroma.map((value, pitch) => (
            <div key={pitch} className="flex w-6 flex-col items-center gap-1">
              <div
                className="w-full rounded-t bg-accent transition-all"
                style={{ height: `${Math.max(2, value * 56)}px`, opacity: 0.35 + value * 0.65 }}
              />
              <span className="text-[9px] text-slate-400">{noteName(pitch)}</span>
            </div>
          ))}
        </div>

        {listening && heard.level <= 0.012 && (
          <p className="mt-4 text-center text-xs text-slate-400">Toque alguma coisa…</p>
        )}
      </section>

      <p className="text-[11px] text-slate-400">
        A detecção compara o que entra com os mesmos moldes de acorde que o analisador usa, mas sem
        as vantagens dele: aqui não há grade de tempo nem tom estimado para desempatar, só o
        presente. Por isso o acorde precisa ser sustentado por alguns quadros antes de aparecer.
      </p>

      {popover && (
        <ChordPopover label={popover} useFlats={false} onClose={() => setPopover(null)} />
      )}
    </div>
  )
}
