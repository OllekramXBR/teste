import { useMemo } from 'react'

import { br } from '../lib/brazilian'
import { INSTRUMENTS, type Instrument } from '../lib/fretboard'
import {
  chordPitchClasses,
  mod12,
  parseLabel,
  QUALITY_LABELS,
  transposeLabel,
} from '../lib/theory'
import type { ChordCard } from './ChordFilmstrip'
import { ChordToneLegend, FretDiagram } from './FretDiagram'
import { PianoDiagram } from './PianoDiagram'

interface Props {
  cards: ChordCard[]
  currentTime: number
  capo: number
  instrument: Instrument['id'] | 'piano'
  useFlats: boolean
  shapeVariant: number
  onCycleShape: () => void
  onOpenPopover: (label: string) => void
  onSeek: (time: number) => void
}

/**
 * The chord being played and the chord coming next, at singing distance.
 *
 * This panel exists for one person: someone with an instrument in hand and a
 * lyric in their throat, glancing at the screen between phrases. That glance
 * has room for exactly two facts — what am I on, what comes next — so those
 * two facts take the whole width of the page, and everything analytical
 * (which key to sing in, what the decoder was sure of) lives somewhere
 * quieter.
 *
 * The next chord shows a countdown in seconds. Bars would be more musical,
 * but seconds are what a beginner counts in, and the number is doing a
 * beginner's job: saying "get ready" at the right moment.
 */
export function NowPlaying({
  cards,
  currentTime,
  capo,
  instrument,
  useFlats,
  shapeVariant,
  onCycleShape,
  onOpenPopover,
  onSeek,
}: Props) {
  const activeIndex = useMemo(() => {
    for (let index = cards.length - 1; index >= 0; index -= 1) {
      if (currentTime >= cards[index].start) return index
    }
    return -1
  }, [cards, currentTime])

  // Before playback reaches the first chord there is still an answer to "what
  // do I put my fingers on": the first chord. Showing it as the coming chord
  // of a stopped song beats showing a dash next to a diagram of nothing.
  const isUpcoming = activeIndex < 0
  const current = isUpcoming ? (cards[0] ?? null) : cards[activeIndex]
  const next = isUpcoming ? (cards[1] ?? null) : (cards[activeIndex + 1] ?? null)

  const parsed = current ? parseLabel(current.label) : null
  const parsedNext = next ? parseLabel(next.label) : null
  const secondsToNext = next ? Math.max(0, Math.ceil(next.start - currentTime)) : null

  // Between the end of one detected span and the start of the next the decoder
  // heard nothing — the label on screen is being carried, like a paper chart
  // carries it, and the badge says so.
  const isHeld = Boolean(!isUpcoming && current && currentTime > current.end + 0.05)

  // The card label is the *shape*; with a capo on, what sounds is that shape
  // moved back up by the capo fret.
  const soundingLabel =
    current && capo > 0 ? transposeLabel(current.label, capo, useFlats) : null

  if (!cards.length) return null

  return (
    <section className="rounded-2xl border border-line bg-panel px-5 py-4">
      <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-4 sm:justify-between">
        {/* What is sounding right now. Re-keyed per card so the change itself
            animates: the pop is the "look up now" signal. */}
        <div key={activeIndex} className="animate-chord-pop flex min-w-0 items-center gap-5">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-ink-faint">
              {isUpcoming ? 'Começa com' : 'Agora'}
            </p>
            <button
              type="button"
              onClick={() => current && onOpenPopover(current.label)}
              disabled={!current}
              title="Ver este acorde em outros instrumentos"
              className="block truncate text-6xl font-bold leading-none tracking-tight text-accent transition hover:opacity-80 sm:text-7xl"
            >
              {current ? br(current.label, useFlats) : '—'}
            </button>
            <p className="mt-1.5 min-h-4 text-xs text-ink-soft">
              {!current && 'Aperte o play e o acorde aparece aqui.'}
              {current && parsed && QUALITY_LABELS[parsed.quality]}
              {current && isHeld && (
                <span
                  className="ml-2 rounded-full bg-canvas px-2 py-0.5 text-[10px] text-ink-faint"
                  title="Nada foi detectado neste tempo; o último acorde segue valendo"
                >
                  sustentado
                </span>
              )}
            </p>
            {soundingLabel && (
              <p className="mt-1 text-[11px] text-ink-faint">
                soa como {br(soundingLabel, useFlats)} · capotraste na casa {capo}
              </p>
            )}
          </div>

          {parsed && (
            <div className="flex shrink-0 flex-col items-center gap-1">
              {instrument === 'piano' ? (
                <PianoDiagram
                  root={parsed.root}
                  notes={chordPitchClasses(parsed.root, parsed.quality).map(mod12)}
                  useFlats={useFlats}
                  width={220}
                />
              ) : (
                <FretDiagram
                  root={parsed.root}
                  quality={parsed.quality}
                  instrument={INSTRUMENTS[instrument] ?? INSTRUMENTS.guitar}
                  useFlats={useFlats}
                  variant={shapeVariant}
                  width={158}
                />
              )}
              {instrument !== 'piano' && (
                <button
                  type="button"
                  onClick={onCycleShape}
                  className="text-[11px] text-accent hover:underline"
                >
                  outra posição ({shapeVariant + 1}/4)
                </button>
              )}
            </div>
          )}
        </div>

        {/* What comes next, dimmed: readable in the same glance without
            competing with the chord that is due right now. */}
        {next && parsedNext && (
          <button
            type="button"
            onClick={() => onSeek(next.start)}
            title="Pular para este acorde"
            className="group flex shrink-0 items-center gap-4 rounded-xl px-3 py-2 text-left opacity-75 transition hover:bg-canvas hover:opacity-100"
          >
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-widest text-ink-faint">
                Próximo
                {secondsToNext !== null && secondsToNext <= 60 && (
                  <span className="ml-1.5 tabular-nums normal-case tracking-normal">
                    em {secondsToNext}s
                  </span>
                )}
              </p>
              <p className="text-4xl font-bold leading-tight tracking-tight text-ink">
                {br(next.label, useFlats)}
              </p>
            </div>
            {instrument === 'piano' ? (
              <PianoDiagram
                root={parsedNext.root}
                notes={chordPitchClasses(parsedNext.root, parsedNext.quality).map(mod12)}
                useFlats={useFlats}
                width={140}
              />
            ) : (
              <FretDiagram
                root={parsedNext.root}
                quality={parsedNext.quality}
                instrument={INSTRUMENTS[instrument] ?? INSTRUMENTS.guitar}
                useFlats={useFlats}
                variant={0}
                width={104}
              />
            )}
          </button>
        )}
      </div>

      {parsed && (
        <div className="mt-2 border-t border-line/60 pt-2">
          <ChordToneLegend quality={parsed.quality} />
        </div>
      )}
    </section>
  )
}
