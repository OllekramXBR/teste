import { useEffect, useMemo, useRef } from 'react'
import type { BeatEvent } from '../lib/api'
import { capoShape, transposeLabel } from '../lib/theory'

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
  loopBars: { start: number; end: number } | null
  onSeek: (time: number) => void
  onBarSelect: (barNumber: number, extend: boolean) => void
  autoScroll: boolean
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
): string {
  if (!label || label === 'N') return ''
  return capoShape(transposeLabel(label, transpose, useFlats), capo, useFlats)
}

export function ChordGrid({
  beats,
  beatsPerBar,
  activeBeat,
  transpose,
  capo,
  useFlats,
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
    return <p className="p-8 text-center text-slate-500">No chords were detected in this track.</p>
  }

  return (
    <div
      ref={containerRef}
      className="max-h-[58vh] overflow-y-auto rounded-xl bg-slate-50 p-3 dark:bg-slate-900/60"
    >
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
                isActive
                  ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40'
                  : 'border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800/60',
                inLoop ? 'ring-2 ring-amber-400/70' : '',
              ].join(' ')}
            >
              <button
                type="button"
                onClick={(event) => onBarSelect(bar.number, event.shiftKey)}
                title="Click to set the loop start, shift-click to set the loop end"
                className="absolute -top-1.5 left-1 rounded bg-slate-200 px-1 text-[9px] font-semibold text-slate-500 hover:bg-amber-300 hover:text-slate-900 dark:bg-slate-700 dark:text-slate-400"
              >
                {bar.number}
              </button>
              <div className="flex gap-1">
                {bar.beats.map((beat) => {
                  const label = displayLabel(beat.label, transpose, capo, useFlats)
                  const previous = beats[beat.index - 1]
                  const isRepeat =
                    previous !== undefined && previous.label === beat.label && previous.bar === beat.bar
                  const isCurrent = beat.index === activeBeat
                  return (
                    <button
                      key={beat.index}
                      type="button"
                      onClick={() => onSeek(beat.time)}
                      title={`Bar ${beat.bar}, beat ${beat.beatInBar} — ${
                        label || 'no chord'
                      } (${Math.round(beat.confidence * 100)}% confident)`}
                      className={[
                        'flex h-12 flex-1 flex-col items-center justify-center rounded text-sm font-semibold transition-all',
                        isCurrent
                          ? 'scale-105 bg-indigo-600 text-white shadow-lg'
                          : 'bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-700/60 dark:text-slate-200 dark:hover:bg-slate-600',
                        isRepeat && !isCurrent ? 'opacity-45' : '',
                      ].join(' ')}
                    >
                      <span>{isRepeat ? '·' : label || '–'}</span>
                      {beat.downbeat && !isCurrent && (
                        <span className="mt-0.5 h-0.5 w-3 rounded bg-indigo-400/70" />
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
