import { useEffect, useMemo, useRef } from 'react'

import type { Lyrics, LyricWord } from '../lib/api'

export interface KaraokeLine {
  start: number
  end: number
  words: LyricWord[]
  chords: { label: string; wordIndex: number }[]
}

interface Props {
  lyrics: Lyrics
  chords: { label: string; start: number }[]
  currentTime: number
  /** Full-bleed, dark, oversized: the version meant to be read from a stand. */
  performance?: boolean
  onSeek?: (time: number) => void
}

/**
 * The lyric, following the recording, with the chord over the syllable it lands
 * on.
 *
 * The word being sung is highlighted from its own timestamp rather than from an
 * interpolation across the line, because a singer holding one syllable for two
 * bars is exactly where an interpolated highlight drifts away from the voice —
 * and that is the moment a performer looks up at the screen.
 *
 * Scrolling keeps the active line above centre rather than in it: what a
 * performer needs to see is the line *after* the one they are singing.
 */
export function KaraokeView({ lyrics, chords, currentTime, performance = false, onSeek }: Props) {
  const lines = useMemo(() => buildLines(lyrics, chords), [lyrics, chords])
  const containerRef = useRef<HTMLDivElement | null>(null)
  const activeRef = useRef<HTMLParagraphElement | null>(null)

  const activeLine = useMemo(() => {
    for (let index = lines.length - 1; index >= 0; index -= 1) {
      if (currentTime >= lines[index].start - 0.3) return index
    }
    return -1
  }, [lines, currentTime])

  useEffect(() => {
    const container = containerRef.current
    const active = activeRef.current
    if (!container || !active) return
    const target = active.offsetTop - container.clientHeight * 0.38
    container.scrollTo({ top: Math.max(0, target), behavior: 'smooth' })
  }, [activeLine])

  if (!lines.length) {
    return (
      <p className="p-8 text-center text-sm text-slate-500">
        Nenhuma letra transcrita para esta música ainda.
      </p>
    )
  }

  return (
    <div
      ref={containerRef}
      className={
        performance
          ? 'h-full overflow-y-auto scroll-smooth bg-slate-950 px-6 py-[35vh] text-slate-400'
          : 'max-h-[28rem] overflow-y-auto scroll-smooth px-2 py-6'
      }
    >
      {lines.map((line, index) => {
        const active = index === activeLine
        return (
          <p
            key={`${line.start}-${index}`}
            ref={active ? activeRef : null}
            onClick={onSeek ? () => onSeek(line.start) : undefined}
            className={[
              'mb-5 cursor-pointer leading-tight transition-colors duration-300',
              performance ? 'text-3xl md:text-5xl' : 'text-lg',
              active ? '' : performance ? 'opacity-40' : 'opacity-60',
            ].join(' ')}
          >
            <ChordRow line={line} performance={performance} />
            <span className="flex flex-wrap items-baseline gap-x-[0.32em]">
              {line.words.map((word, wordIndex) => {
                const sung = currentTime >= word.start
                const singing = currentTime >= word.start && currentTime < word.end + 0.08
                return (
                  <span
                    key={`${word.start}-${wordIndex}`}
                    className={[
                      'transition-colors duration-150',
                      singing
                        ? 'text-sky-400'
                        : sung && active
                          ? performance
                            ? 'text-white'
                            : 'text-slate-900 dark:text-slate-100'
                          : '',
                      // A word the recogniser was unsure of is dimmed rather
                      // than hidden: on stage a wrong word you can see is
                      // recoverable, a missing one is not.
                      word.probability < 0.4 ? 'italic opacity-70' : '',
                    ].join(' ')}
                  >
                    {word.text}
                  </span>
                )
              })}
            </span>
          </p>
        )
      })}
    </div>
  )
}

function ChordRow({ line, performance }: { line: KaraokeLine; performance: boolean }) {
  if (!line.chords.length) return null
  return (
    <span
      className={[
        'mb-1 flex flex-wrap gap-x-[0.32em] font-semibold',
        performance ? 'text-xl text-amber-400 md:text-2xl' : 'text-sm text-indigo-500',
      ].join(' ')}
    >
      {line.words.map((word, index) => {
        const here = line.chords.filter((chord) => chord.wordIndex === index)
        return (
          <span key={`slot-${index}`} className="relative">
            {/* The invisible copy of the word is what gives the chord the exact
                width of the syllable it belongs to, without a monospaced font
                and without measuring anything at runtime. */}
            <span className="invisible">{word.text}</span>
            {here.length > 0 && (
              <span className="absolute left-0 top-0 whitespace-nowrap">
                {here.map((chord) => chord.label).join(' ')}
              </span>
            )}
          </span>
        )
      })}
    </span>
  )
}

/** Group words into sung phrases and attach each chord to the word it lands on. */
export function buildLines(
  lyrics: Lyrics,
  chords: { label: string; start: number }[],
): KaraokeLine[] {
  const segments = lyrics.segments ?? []
  const lines: KaraokeLine[] = []

  let current: LyricWord[] = []
  let phrase = -2

  const flush = () => {
    if (!current.length) return
    lines.push({
      start: current[0].start,
      end: current[current.length - 1].end,
      words: current,
      chords: [],
    })
    current = []
  }

  for (const word of lyrics.words ?? []) {
    const index = segments.findIndex(
      (segment) => word.start >= segment.start - 0.05 && word.start <= segment.end + 0.05,
    )
    if (current.length && index !== phrase && index >= 0) flush()
    phrase = index
    current.push(word)
  }
  flush()

  for (const chord of chords) {
    // A chord that changes during a breath belongs to the line it prepares, so
    // the search is for the first line that has not finished yet.
    const lineIndex = lines.findIndex((line) => chord.start < line.end)
    if (lineIndex < 0) continue
    const line = lines[lineIndex]
    if (chord.start < line.start - 4) continue // an instrumental stretch, not this line
    let wordIndex = line.words.findIndex((word) => word.end > chord.start)
    if (wordIndex < 0) wordIndex = line.words.length - 1
    const last = line.chords[line.chords.length - 1]
    if (last && last.wordIndex === wordIndex && last.label === chord.label) continue
    line.chords.push({ label: chord.label, wordIndex })
  }

  return lines
}
