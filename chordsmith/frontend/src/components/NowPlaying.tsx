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
  /** Beat position inside the current bar, 1-based; undefined before play. */
  beatInBar?: number
  beatsPerBar?: number
  /** True while the trainer holds the tape for the next chord. */
  trainingPaused?: boolean
  onCycleShape: () => void
  onOpenPopover: (label: string) => void
  onSeek: (time: number) => void
}

/**
 * The stage: the chord being played, written in light.
 *
 * This panel exists for one person — someone with an instrument in hand and a
 * lyric in their throat, glancing up between phrases. That glance has room
 * for exactly two facts, what am I on and what comes next, so those two facts
 * get the whole width, the biggest type in the app, and the only glow. The
 * thin bar underneath drains toward the moment the next chord lands, which is
 * the "get ready" a band mate would give with a nod.
 */
export function NowPlaying({
  cards,
  currentTime,
  capo,
  instrument,
  useFlats,
  shapeVariant,
  beatInBar,
  beatsPerBar = 4,
  trainingPaused = false,
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

  // How far through this chord we are, 0..1, draining toward the next change.
  const progress = useMemo(() => {
    if (!current || isUpcoming) return 0
    const end = next ? next.start : current.end
    const span = end - current.start
    if (span <= 0) return 1
    return Math.min(1, Math.max(0, (currentTime - current.start) / span))
  }, [current, next, currentTime, isUpcoming])

  if (!cards.length) return null

  return (
    <section className="glass relative overflow-hidden rounded-2xl px-6 pb-5 pt-4">
      {/* The throw of light behind the letters. It breathes slower than any
          tempo, so it reads as a lamp and not as a metronome that disagrees
          with the song. */}
      <div
        aria-hidden="true"
        className="animate-breathe pointer-events-none absolute -left-16 -top-24 h-72 w-96 rounded-full"
        style={{
          background:
            'radial-gradient(closest-side, color-mix(in oklab, var(--color-accent) 22%, transparent), transparent 72%)',
        }}
      />

      <div className="relative flex flex-wrap items-center justify-center gap-x-10 gap-y-5 sm:justify-between">
        {/* What is sounding right now. Re-keyed per card so the change itself
            animates: the pop is the "look up now" signal. */}
        <div key={activeIndex} className="animate-chord-pop flex min-w-0 items-center gap-6">
          <div className="min-w-0">
            <p className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.22em] text-ink-faint">
              {isUpcoming ? 'Começa com' : 'Agora'}
              {/* The bar pulse: one dot per beat, the sounding one lit. A
                  player keeping time glances here instead of counting. */}
              {beatInBar !== undefined && !isUpcoming && (
                <span className="flex items-center gap-1" aria-hidden="true">
                  {Array.from({ length: beatsPerBar }, (_, index) => (
                    <span
                      key={index}
                      className={[
                        'h-1.5 w-1.5 rounded-full transition-all duration-100',
                        index + 1 === beatInBar
                          ? index === 0
                            ? 'scale-125 bg-flame'
                            : 'scale-125 bg-accent'
                          : 'bg-line',
                      ].join(' ')}
                    />
                  ))}
                </span>
              )}
            </p>
            <button
              type="button"
              onClick={() => current && onOpenPopover(current.label)}
              disabled={!current}
              title="Ver este acorde em outros instrumentos"
              className="text-neon block truncate pb-1 pr-1 text-7xl font-extrabold leading-none tracking-tight transition hover:brightness-110 sm:text-8xl"
            >
              {current ? br(current.label, useFlats) : '—'}
            </button>
            <p className="mt-1 min-h-4 text-xs text-ink-soft">
              {!current && 'Aperte o play e o acorde aparece aqui.'}
              {current && parsed && QUALITY_LABELS[parsed.quality]}
              {current && isHeld && (
                <span
                  className="ml-2 rounded-full border border-line/60 px-2 py-0.5 text-[10px] text-ink-faint"
                  title="Nada foi detectado neste tempo; o último acorde segue valendo"
                >
                  sustentado
                </span>
              )}
            </p>
            {soundingLabel && (
              <p className="mt-1 text-[11px] text-ink-faint">
                soa como <span className="text-flame">{br(soundingLabel, useFlats)}</span> ·
                capotraste na casa {capo}
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
                  width={230}
                />
              ) : (
                <FretDiagram
                  root={parsed.root}
                  quality={parsed.quality}
                  instrument={INSTRUMENTS[instrument] ?? INSTRUMENTS.guitar}
                  useFlats={useFlats}
                  variant={shapeVariant}
                  width={164}
                />
              )}
              {instrument !== 'piano' && (
                <button
                  type="button"
                  onClick={onCycleShape}
                  className="text-[11px] font-medium text-accent transition hover:brightness-125"
                >
                  outra posição ({shapeVariant + 1}/4)
                </button>
              )}
            </div>
          )}
        </div>

        {/* What comes next, quiet: readable in the same glance without
            competing with the chord that is due right now. */}
        {next && parsedNext && (
          <button
            type="button"
            onClick={() => onSeek(next.start)}
            title="Pular para este acorde"
            className="group flex shrink-0 items-center gap-4 rounded-xl border border-transparent px-4 py-3 text-left opacity-80 transition hover:border-line/60 hover:bg-canvas/50 hover:opacity-100"
          >
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-ink-faint">
                Próximo
                {secondsToNext !== null && secondsToNext <= 60 && (
                  <span className="ml-1.5 tabular-nums normal-case tracking-normal text-flame">
                    em {secondsToNext}s
                  </span>
                )}
              </p>
              <p className="text-4xl font-extrabold leading-tight tracking-tight text-ink">
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

      {trainingPaused && next && (
        <p className="relative mt-3 rounded-lg border border-flame/40 bg-flame-soft px-3 py-2 text-center text-xs font-medium text-ink">
          Treino: monte <span className="font-bold">{br(next.label, useFlats)}</span> com calma —
          espaço (ou play) continua.
        </p>
      )}

      {/* Time draining toward the next change — the nod that says "ready". */}
      <div className="relative mt-4 h-1 overflow-hidden rounded-full bg-line/50">
        <div
          className="h-full rounded-full"
          style={{
            width: `${progress * 100}%`,
            background: 'linear-gradient(90deg, var(--color-accent), var(--color-flame))',
          }}
        />
      </div>

      {parsed && (
        <div className="relative mt-3">
          <ChordToneLegend quality={parsed.quality} />
        </div>
      )}
    </section>
  )
}
