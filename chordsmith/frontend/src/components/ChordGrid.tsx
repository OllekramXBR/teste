import { useEffect, useMemo, useRef } from 'react'
import type { BeatEvent } from '../lib/api'
import { simplify as simplifyLabel } from '../lib/brazilian'
import {
  capoShape,
  chordFunction,
  mod12,
  transposeLabel,
  type HarmonicFunction,
} from '../lib/theory'

export interface Bar {
  number: number
  beats: BeatEvent[]
  start: number
  end: number
}

interface ChordGridProps {
  beats: BeatEvent[]
  beatsPerBar: number
  activeBeat: number
  transpose: number
  capo: number
  useFlats: boolean
  /** Collapse decoder extensions to the triad a hand actually makes. */
  simplify?: boolean
  /** Key of the song (sounding), for the harmonic-function stripes. */
  keyTonic?: number
  keyMode?: string
  loopBars: { start: number; end: number } | null
  onSeek: (time: number) => void
  onBarSelect: (barNumber: number, extend: boolean) => void
  autoScroll: boolean
}

/** Stripe colour for each harmonic function; borrowed chords get the line. */
const FUNC_STRIPE: Record<HarmonicFunction, string> = {
  T: 'bg-accent',
  SD: 'bg-flame',
  D: 'bg-rose-400',
}

/** Group the flat beat list into bars, keeping any pickup beats in bar 1. */
export function groupIntoBars(beats: BeatEvent[]): Bar[] {
  const bars = new Map<number, BeatEvent[]>()
  for (const beat of beats) {
    const number = Math.max(beat.bar, 1)
    const existing = bars.get(number)
    if (existing) existing.push(beat)
    else bars.set(number, [beat])
  }
  return [...bars.entries()]
    .sort(([a], [b]) => a - b)
    .map(([number, barBeats]) => ({
      number,
      beats: barBeats,
      start: barBeats[0].time,
      end: barBeats[barBeats.length - 1].time + barBeats[barBeats.length - 1].duration,
    }))
}

/** Label to display for a beat once transposition and capo are applied. */
export function displayLabel(
  label: string,
  transpose: number,
  capo: number,
  useFlats: boolean,
  simplify = false,
): string {
  if (!label || label === 'N') return ''
  const reduced = simplify ? simplifyLabel(label, useFlats) : label
  return capoShape(transposeLabel(reduced, transpose, useFlats), capo, useFlats)
}

export function ChordGrid({
  beats,
  beatsPerBar,
  activeBeat,
  transpose,
  capo,
  useFlats,
  simplify = false,
  keyTonic,
  keyMode,
  loopBars,
  onSeek,
  onBarSelect,
  autoScroll,
}: ChordGridProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const activeBarRef = useRef<HTMLDivElement | null>(null)
  const bars = useMemo(() => groupIntoBars(beats), [beats])

  const activeBarNumber = beats[activeBeat]?.bar ?? -1

  useEffect(() => {
    if (!autoScroll || !activeBarRef.current || !containerRef.current) return
    const container = containerRef.current
    const element = activeBarRef.current
    const containerBox = container.getBoundingClientRect()
    const elementBox = element.getBoundingClientRect()
    const above = elementBox.top < containerBox.top + 40
    const below = elementBox.bottom > containerBox.bottom - 40
    if (above || below) {
      container.scrollTo({
        top: container.scrollTop + (elementBox.top - containerBox.top) - containerBox.height / 3,
        behavior: 'smooth',
      })
    }
  }, [activeBarNumber, autoScroll])

  if (!bars.length) {
    return <p className="p-8 text-center text-ink-soft">Nenhum acorde detectado nesta faixa.</p>
  }

  const showFunctions = keyTonic !== undefined && keyMode !== undefined
  // Functions are read against the *sounding* key: transpose moves both the
  // chord and the tonic, so the stripe never changes when the song is moved.
  const soundingTonic = showFunctions ? mod12(keyTonic! + transpose) : 0

  return (
    <div
      ref={containerRef}
      className="max-h-[58vh] overflow-y-auto rounded-xl bg-canvas p-3"
    >
      {showFunctions && (
        <p className="mb-2 flex items-center justify-end gap-3 text-[10px] text-ink-faint">
          <span className="flex items-center gap-1">
            <span className="h-1 w-4 rounded bg-accent" /> repouso
          </span>
          <span className="flex items-center gap-1">
            <span className="h-1 w-4 rounded bg-flame" /> caminho
          </span>
          <span className="flex items-center gap-1">
            <span className="h-1 w-4 rounded bg-rose-400" /> tensão
          </span>
          <span className="flex items-center gap-1">
            <span className="h-1 w-4 rounded border border-dashed border-line" /> fora do campo
          </span>
        </p>
      )}
      <div
        className="grid gap-2"
        style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${beatsPerBar * 52}px, 1fr))` }}
      >
        {bars.map((bar) => {
          const isActive = bar.number === activeBarNumber
          const inLoop = loopBars ? bar.number >= loopBars.start && bar.number <= loopBars.end : false
          return (
            <div
              key={bar.number}
              ref={isActive ? activeBarRef : undefined}
              className={[
                'group relative rounded-lg border p-1 transition-colors',
                isActive ? 'border-accent bg-accent-soft' : 'border-line bg-panel',
                inLoop ? 'ring-2 ring-amber-400/70' : '',
              ].join(' ')}
            >
              <button
                type="button"
                onClick={(event) => onBarSelect(bar.number, event.shiftKey)}
                title="Clique para marcar o início do loop, shift-clique para o fim"
                className="absolute -top-1.5 left-1 rounded bg-canvas px-1 text-[9px] font-semibold text-ink-soft hover:bg-amber-300 hover:text-slate-900"
              >
                {bar.number}
              </button>
              <div className="flex gap-1">
                {bar.beats.map((beat) => {
                  const label = displayLabel(beat.label, transpose, capo, useFlats, simplify)
                  const previous = beats[beat.index - 1]
                  const isRepeat =
                    previous !== undefined && previous.label === beat.label && previous.bar === beat.bar
                  const isCurrent = beat.index === activeBeat
                  // Stripe on the first beat of each chord: its role in the key.
                  const func =
                    showFunctions && !isRepeat && beat.root !== null
                      ? chordFunction(mod12(beat.root + transpose), soundingTonic, keyMode!)
                      : undefined
                  return (
                    <button
                      key={beat.index}
                      type="button"
                      onClick={() => onSeek(beat.time)}
                      title={`Compasso ${beat.bar}, tempo ${beat.beatInBar} — ${
                        label || 'sem acorde'
                      } (${Math.round(beat.confidence * 100)}% de confiança)`}
                      className={[
                        'flex h-12 flex-1 flex-col items-center justify-center rounded text-sm font-semibold transition-all duration-200 ease-out',
                        isCurrent
                          ? 'scale-105 text-canvas shadow-[0_0_16px_color-mix(in_oklab,var(--color-accent)_50%,transparent)]'
                          : 'bg-canvas text-ink hover:bg-accent-soft',
                        isRepeat && !isCurrent ? 'opacity-45' : '',
                      ].join(' ')}
                      style={
                        isCurrent
                          ? {
                              background:
                                'linear-gradient(135deg, var(--color-accent), color-mix(in oklab, var(--color-accent) 55%, var(--color-flame)))',
                            }
                          : undefined
                      }
                    >
                      <span>{isRepeat ? '·' : label || '–'}</span>
                      {func !== undefined && !isCurrent && (
                        <span
                          className={[
                            'mt-0.5 h-0.5 w-4 rounded',
                            func === null
                              ? 'border border-dashed border-line'
                              : FUNC_STRIPE[func],
                          ].join(' ')}
                          title={
                            func === null
                              ? 'fora do campo harmônico'
                              : func === 'T'
                                ? 'tônica — repouso'
                                : func === 'SD'
                                  ? 'subdominante — caminho'
                                  : 'dominante — tensão'
                          }
                        />
                      )}
                      {func === undefined && beat.downbeat && !isCurrent && (
                        <span className="mt-0.5 h-0.5 w-3 rounded bg-accent/60" />
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
