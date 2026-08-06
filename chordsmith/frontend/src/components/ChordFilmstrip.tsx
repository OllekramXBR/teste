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

    // Centred, not left of centre. On a tablet propped up two metres away the
    // eye goes to the middle of the strip and stays there, so the chord being
    // played has to be what is already under it — and what comes next is then
    // visible on the right without anybody hunting for the current one first.
    const containerBox = container.getBoundingClientRect()
    const activeBox = active.getBoundingClientRect()
    const delta = activeBox.left - containerBox.left
    container.scrollTo({
      left: container.scrollLeft + delta - containerBox.width / 2 + activeBox.width / 2,
      behavior: 'smooth',
    })
  }, [activeIndex])

  if (!cards.length) {
    return (
      <p className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-ink-soft ">
        Nenhum acorde detectado nesta música.
      </p>
    )
  }

  return (
    <div
      ref={containerRef}
      // The padding on both ends is what lets the first and last chord reach
      // the middle at all: without it the strip runs out of scroll and they sit
      // stranded against an edge.
      className="flex items-center gap-4 overflow-x-auto rounded-xl border border-line bg-panel px-[45%] py-5"
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
              'flex shrink-0 flex-col items-center gap-2 rounded-xl px-4 py-3 transition-all duration-300',
              // The played chord is bigger, not just tinted. From a stand,
              // colour alone is a weak signal and size is an unmissable one.
              active
                ? 'scale-100 bg-accent-soft opacity-100'
                : 'scale-[0.78] opacity-40 hover:opacity-75',
            ].join(' ')}
          >
            <span
              className={[
                'font-bold tracking-tight',
                active ? 'text-3xl text-accent md:text-4xl' : 'text-xl',
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
                  width={active ? 210 : 145}
                />
              ) : (
                <FretDiagram
                  root={parsed.root}
                  quality={parsed.quality}
                  instrument={INSTRUMENTS[instrument] ?? INSTRUMENTS.guitar}
                  useFlats={useFlats}
                  variant={0}
                  width={active ? 168 : 116}
                />
              ))}
            <span className="text-[10px] tabular-nums text-ink-faint">
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
