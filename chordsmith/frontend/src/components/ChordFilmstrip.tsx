import { useEffect, useMemo, useRef } from 'react'

import type { ChordSpan } from '../lib/api'
import { displayLabel } from './ChordGrid'
import { br } from '../lib/brazilian'
import { INSTRUMENTS, type Instrument } from '../lib/fretboard'
import { parseLabel } from '../lib/theory'
import { FretDiagram } from './FretDiagram'
import { PianoDiagram } from './PianoDiagram'

interface Props {
  chords: ChordSpan[]
  transpose: number
  capo: number
  useFlats: boolean
  simplify: boolean
  currentTime: number
  instrument: Instrument['id'] | 'piano'
  onSeek?: (time: number) => void
}

/**
 * The chords of the song as a strip of diagrams that moves with the music.
 *
 * The grid above tells you *when* a chord happens; this tells you *how* to
 * play it, in the order you will need to. That is a different question and it
 * is the one someone learning a song is actually asking, so it gets its own
 * view rather than a corner of another one.
 *
 * The strip scrolls to keep the current chord left of centre rather than in
 * it. What a learner needs to see is the shape they are about to change to,
 * and a chord centred is a chord with its future off screen.
 */
export function ChordFilmstrip({
  chords,
  transpose,
  capo,
  useFlats,
  simplify,
  currentTime,
  instrument,
  onSeek,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const activeRef = useRef<HTMLButtonElement | null>(null)

  // Consecutive spans that reduce to the same shape are one card: a learner
  // does not need the same diagram drawn four times because the decoder split
  // it across four beats.
  const cards = useMemo(() => {
    const out: { label: string; start: number; end: number }[] = []
    for (const span of chords) {
      if (span.root === null) continue
      const label = displayLabel(span.label, transpose, capo, useFlats, simplify)
      if (!label) continue
      const last = out[out.length - 1]
      if (last && last.label === label) {
        last.end = span.end
        continue
      }
      out.push({ label, start: span.start, end: span.end })
    }
    return out
  }, [chords, transpose, capo, useFlats, simplify])

  const activeIndex = useMemo(() => {
    for (let index = cards.length - 1; index >= 0; index -= 1) {
      if (currentTime >= cards[index].start) return index
    }
    return -1
  }, [cards, currentTime])

  useEffect(() => {
    const container = containerRef.current
    const active = activeRef.current
    if (!container || !active) return
    const delta = active.getBoundingClientRect().left - container.getBoundingClientRect().left
    container.scrollTo({
      left: container.scrollLeft + delta - container.clientWidth * 0.28,
      behavior: 'smooth',
    })
  }, [activeIndex])

  if (!cards.length) {
    return (
      <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500 dark:border-slate-700">
        Nenhum acorde detectado nesta música.
      </p>
    )
  }

  return (
    <div
      ref={containerRef}
      className="flex gap-3 overflow-x-auto rounded-xl border border-slate-200 bg-panel p-4 dark:border-slate-800"
    >
      {cards.map((card, index) => {
        const parsed = parseLabel(card.label)
        const active = index === activeIndex
        return (
          <button
            key={`${card.start}-${index}`}
            ref={active ? activeRef : null}
            type="button"
            onClick={() => onSeek?.(card.start)}
            className={[
              'flex shrink-0 flex-col items-center gap-1.5 rounded-lg px-3 py-2 transition',
              active ? 'bg-accent-soft' : 'opacity-55 hover:opacity-100',
            ].join(' ')}
          >
            <span
              className={[
                'text-lg font-bold tracking-tight',
                active ? 'text-accent' : '',
              ].join(' ')}
            >
              {br(card.label, useFlats)}
            </span>
            {parsed &&
              (instrument === 'piano' ? (
                <PianoDiagram
                  root={parsed.root}
                  notes={[parsed.root]}
                  useFlats={useFlats}
                  width={120}
                />
              ) : (
                <FretDiagram
                  root={parsed.root}
                  quality={parsed.quality}
                  instrument={INSTRUMENTS[instrument] ?? INSTRUMENTS.guitar}
                  useFlats={useFlats}
                  variant={0}
                  width={92}
                />
              ))}
            <span className="text-[10px] tabular-nums text-slate-400">
              {formatTime(card.start)}
            </span>
          </button>
        )
      })}
    </div>
  )
}

function formatTime(seconds: number): string {
  const whole = Math.floor(seconds)
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`
}
