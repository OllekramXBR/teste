import { useEffect, useState } from 'react'

import { INSTRUMENTS, type Instrument } from '../lib/fretboard'
import { chordPitchClasses, mod12, noteName, parseLabel, QUALITY_LABELS } from '../lib/theory'
import { ChordToneLegend, FretDiagram } from './FretDiagram'
import { PianoDiagram } from './PianoDiagram'

const INSTRUMENT_KEY = 'metatron.chordInstrument.v1'
const SHAPES = 4

export type DiagramInstrument = Instrument['id'] | 'piano'

const ORDER: DiagramInstrument[] = [
  'guitar',
  'piano',
  'cavaquinho',
  'ukulele',
  'viola',
  'bass',
  'mandolin',
  'banjo',
]

const LABELS: Record<DiagramInstrument, string> = {
  guitar: 'Violão',
  piano: 'Teclado',
  cavaquinho: 'Cavaquinho',
  ukulele: 'Ukulele',
  viola: 'Viola caipira',
  bass: 'Baixo',
  mandolin: 'Bandolim',
  banjo: 'Banjo',
}

interface Props {
  label: string
  useFlats: boolean
  onClose: () => void
}

/**
 * How to play the chord you just tapped, on whichever instrument you hold.
 *
 * The shapes are searched for rather than looked up, so every chord in the
 * vocabulary works on every instrument here, including the two that chord sites
 * generally ignore — the cavaquinho and the viola caipira. Adding an instrument
 * is a tuning and nothing else.
 *
 * The chosen instrument is remembered, because someone who plays cavaquinho
 * plays cavaquinho on the next chord too.
 */
export function ChordPopover({ label, useFlats, onClose }: Props) {
  const [instrument, setInstrument] = useState<DiagramInstrument>(
    () => (localStorage.getItem(INSTRUMENT_KEY) as DiagramInstrument) || 'guitar',
  )
  const [variant, setVariant] = useState(0)

  useEffect(() => {
    localStorage.setItem(INSTRUMENT_KEY, instrument)
  }, [instrument])

  useEffect(() => {
    setVariant(0)
  }, [label, instrument])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const parsed = parseLabel(label)

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/60 p-4 sm:items-center"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="w-full max-w-md rounded-2xl border border-line bg-panel p-5 shadow-xl "
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-label={`Acorde ${label}`}
      >
        <div className="mb-4 flex items-baseline justify-between gap-3">
          <div>
            <p className="text-3xl font-bold tracking-tight">{label}</p>
            {parsed && (
              <p className="text-xs text-ink-soft">
                {QUALITY_LABELS[parsed.quality]} ·{' '}
                {chordPitchClasses(parsed.root, parsed.quality)
                  .map((pitch) => noteName(mod12(pitch), useFlats))
                  .join(' ')}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="h-9 w-9 shrink-0 rounded-full border border-line text-sm text-ink-soft "
            aria-label="Fechar"
          >
            ✕
          </button>
        </div>

        <div className="mb-4 flex flex-wrap gap-1.5">
          {ORDER.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setInstrument(option)}
              className={[
                'rounded-full border px-3 py-1 text-xs font-medium transition',
                instrument === option
                  ? 'border-ink bg-ink text-canvas'
                  : 'border-line text-ink-soft',
              ].join(' ')}
            >
              {LABELS[option]}
            </button>
          ))}
        </div>

        {!parsed ? (
          <p className="py-8 text-center text-sm text-ink-soft">
            Não sei desenhar “{label}”.
          </p>
        ) : instrument === 'piano' ? (
          <div className="flex justify-center">
            <PianoDiagram
              root={parsed.root}
              notes={chordPitchClasses(parsed.root, parsed.quality).map((pitch) => mod12(pitch))}
              useFlats={useFlats}
              width={320}
            />
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <FretDiagram
              root={parsed.root}
              quality={parsed.quality}
              instrument={INSTRUMENTS[instrument]}
              useFlats={useFlats}
              variant={variant}
              width={190}
            />
            <button
              type="button"
              onClick={() => setVariant((previous) => (previous + 1) % SHAPES)}
              className="rounded-full border border-line px-4 py-1.5 text-xs font-medium "
            >
              outra posição ({variant + 1}/{SHAPES})
            </button>
          </div>
        )}

        {parsed && instrument !== 'piano' && (
          <div className="mt-3 flex justify-center">
            <ChordToneLegend quality={parsed.quality} />
          </div>
        )}
      </div>
    </div>
  )
}
