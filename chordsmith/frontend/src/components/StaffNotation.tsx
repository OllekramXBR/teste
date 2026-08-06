import { useMemo } from 'react'

import { FLAT_NAMES, SHARP_NAMES } from '../lib/theory'

export interface StaffNote {
  midi: number
  start: number
  end: number
  velocity: number
}

export interface StaffTrack {
  name: string
  program: number
  notes: StaffNote[]
}

interface Props {
  track: StaffTrack
  bpm: number
  beatsPerBar: number
  useFlats?: boolean
  currentTime?: number
  /** How many bars to draw per line. */
  barsPerLine?: number
  onSeek?: (time: number) => void
}

const LINE_GAP = 8 // pixels between two staff lines
const STAFF_HEIGHT = LINE_GAP * 4
const TOP = 34 // room above the staff for ledger lines and high notes
const BOTTOM = 34
const BAR_WIDTH = 132
const LEFT = 34

/** Diatonic step of each pitch class within an octave: C D E F G A B. */
const STEP_OF_PITCH_CLASS = [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6]
const IS_SHARPENED = [false, true, false, true, false, false, true, false, true, false, true, false]

/** Note durations we are willing to draw, longest first, in beats. */
const DURATIONS: { beats: number; filled: boolean; stem: boolean; flags: number }[] = [
  { beats: 4, filled: false, stem: false, flags: 0 },
  { beats: 2, filled: false, stem: true, flags: 0 },
  { beats: 1, filled: true, stem: true, flags: 0 },
  { beats: 0.5, filled: true, stem: true, flags: 1 },
  { beats: 0.25, filled: true, stem: true, flags: 2 },
]

/**
 * A transcribed line drawn as staff notation.
 *
 * This is written rather than pulled from a notation library on purpose: the
 * input is a pitch tracker's output, not an engraved score, and every real
 * notation engine wants a well-formed rhythmic structure it does not have.
 * Feeding a transcription to one produces either an error or a page of
 * thirty-second-note tuplets. Rounding to the nearest playable duration and
 * drawing it directly is honest about what the data is: a readable picture of
 * what was played, not a publisher's edition.
 *
 * Which is also why the clef follows the music. A bass line on a treble staff
 * is legible only to someone who does not need it.
 */
export function StaffNotation({
  track,
  bpm,
  beatsPerBar,
  useFlats = false,
  currentTime = 0,
  barsPerLine = 4,
  onSeek,
}: Props) {
  const layout = useMemo(
    () => layoutTrack(track, bpm, beatsPerBar, barsPerLine),
    [track, bpm, beatsPerBar, barsPerLine],
  )

  if (!track.notes.length) {
    return (
      <p className="px-4 py-6 text-center text-xs text-slate-500">
        Nada foi transcrito nesta pista.
      </p>
    )
  }

  const width = LEFT + barsPerLine * BAR_WIDTH + 16
  const lineHeight = TOP + STAFF_HEIGHT + BOTTOM

  return (
    <div className="overflow-x-auto">
      <svg
        width={width}
        height={lineHeight * layout.lines.length}
        viewBox={`0 0 ${width} ${lineHeight * layout.lines.length}`}
        className="text-slate-900 dark:text-slate-100"
        role="img"
        aria-label={`Partitura: ${track.name}`}
      >
        {layout.lines.map((line, lineIndex) => {
          const originY = lineIndex * lineHeight + TOP
          return (
            <g key={lineIndex}>
              {[0, 1, 2, 3, 4].map((index) => (
                <line
                  key={index}
                  x1={LEFT}
                  x2={width - 16}
                  y1={originY + index * LINE_GAP}
                  y2={originY + index * LINE_GAP}
                  stroke="currentColor"
                  strokeWidth={0.7}
                  opacity={0.45}
                />
              ))}

              <text
                x={4}
                y={originY + (layout.clef === 'bass' ? LINE_GAP * 1.6 : LINE_GAP * 3.4)}
                fontSize={layout.clef === 'bass' ? 26 : 30}
                fill="currentColor"
              >
                {layout.clef === 'bass' ? '𝄢' : '𝄞'}
              </text>

              {line.bars.map((bar, barIndex) => (
                <line
                  key={`bar-${barIndex}`}
                  x1={LEFT + (barIndex + 1) * BAR_WIDTH}
                  x2={LEFT + (barIndex + 1) * BAR_WIDTH}
                  y1={originY}
                  y2={originY + STAFF_HEIGHT}
                  stroke="currentColor"
                  strokeWidth={0.9}
                  opacity={0.5}
                />
              ))}

              {line.notes.map((note, index) => {
                const y = originY + note.offset * (LINE_GAP / 2)
                const playing = currentTime >= note.start && currentTime < note.end
                return (
                  <g
                    key={index}
                    onClick={onSeek ? () => onSeek(note.start) : undefined}
                    className={onSeek ? 'cursor-pointer' : undefined}
                    fill="currentColor"
                    opacity={playing ? 1 : 0.85}
                  >
                    {ledgerLines(note.offset).map((step) => (
                      <line
                        key={step}
                        x1={note.x - 7}
                        x2={note.x + 7}
                        y1={originY + step * (LINE_GAP / 2)}
                        y2={originY + step * (LINE_GAP / 2)}
                        stroke="currentColor"
                        strokeWidth={0.7}
                        opacity={0.6}
                      />
                    ))}

                    {note.accidental && (
                      <text x={note.x - 16} y={y + 4} fontSize={12} fill="currentColor">
                        {note.accidental}
                      </text>
                    )}

                    <ellipse
                      cx={note.x}
                      cy={y}
                      rx={4.6}
                      ry={3.4}
                      transform={`rotate(-20 ${note.x} ${y})`}
                      fill={note.filled ? (playing ? '#0ea5e9' : 'currentColor') : 'none'}
                      stroke={playing ? '#0ea5e9' : 'currentColor'}
                      strokeWidth={note.filled ? 0 : 1.1}
                    />

                    {note.stem && (
                      <line
                        x1={note.up ? note.x + 4.4 : note.x - 4.4}
                        x2={note.up ? note.x + 4.4 : note.x - 4.4}
                        y1={y}
                        y2={y + (note.up ? -24 : 24)}
                        stroke={playing ? '#0ea5e9' : 'currentColor'}
                        strokeWidth={1}
                      />
                    )}

                    {Array.from({ length: note.flags }, (_, flag) => (
                      <line
                        key={flag}
                        x1={note.up ? note.x + 4.4 : note.x - 4.4}
                        x2={note.up ? note.x + 11 : note.x - 11}
                        y1={y + (note.up ? -24 + flag * 5 : 24 - flag * 5)}
                        y2={y + (note.up ? -17 + flag * 5 : 17 - flag * 5)}
                        stroke={playing ? '#0ea5e9' : 'currentColor'}
                        strokeWidth={1.1}
                      />
                    ))}
                  </g>
                )
              })}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

interface PlacedNote {
  x: number
  offset: number
  filled: boolean
  stem: boolean
  flags: number
  up: boolean
  accidental: string | null
  start: number
  end: number
}

function layoutTrack(track: StaffTrack, bpm: number, beatsPerBar: number, barsPerLine: number) {
  const secondsPerBeat = bpm > 0 ? 60 / bpm : 0.5
  const secondsPerBar = secondsPerBeat * beatsPerBar

  const median = [...track.notes].sort((a, b) => a.midi - b.midi)[
    Math.floor(track.notes.length / 2)
  ]
  // Middle C is 60. A line sitting mostly below it belongs on a bass staff.
  const clef: 'treble' | 'bass' = (median?.midi ?? 60) < 57 ? 'bass' : 'treble'
  // Staff offsets are counted in half-spaces downward from the top line, which
  // is F5 on a treble staff and A3 on a bass staff.
  const reference = clef === 'bass' ? { step: stepOf(45), midi: 45 } : { step: stepOf(65), midi: 65 }

  const lastEnd = Math.max(...track.notes.map((note) => note.end))
  const totalBars = Math.max(1, Math.ceil(lastEnd / secondsPerBar))
  const lineCount = Math.ceil(totalBars / barsPerLine)

  const lines: { bars: number[]; notes: PlacedNote[] }[] = Array.from(
    { length: lineCount },
    (_, index) => ({
      bars: Array.from({ length: barsPerLine }, (_, bar) => index * barsPerLine + bar),
      notes: [],
    }),
  )

  for (const note of track.notes) {
    const bar = Math.floor(note.start / secondsPerBar)
    const lineIndex = Math.floor(bar / barsPerLine)
    if (lineIndex >= lines.length) continue

    const withinBar = (note.start % secondsPerBar) / secondsPerBar
    const barInLine = bar % barsPerLine
    const x = LEFT + (barInLine + withinBar) * BAR_WIDTH + 12

    const step = stepOf(note.midi)
    const offset = (reference.step - step) * 1 + 0 // one half-space per diatonic step
    const beats = (note.end - note.start) / secondsPerBeat
    const shape =
      DURATIONS.find((option) => beats >= option.beats * 0.75) ?? DURATIONS[DURATIONS.length - 1]

    const pitchClass = ((note.midi % 12) + 12) % 12
    const names = useFlatNames(pitchClass) ? FLAT_NAMES : SHARP_NAMES

    lines[lineIndex].notes.push({
      x,
      offset,
      filled: shape.filled,
      stem: shape.stem,
      flags: shape.flags,
      up: offset > 4,
      accidental: IS_SHARPENED[pitchClass] ? (names === FLAT_NAMES ? '♭' : '♯') : null,
      start: note.start,
      end: note.end,
    })
  }

  return { clef, lines }
}

/** Diatonic position of a MIDI note, counted in steps from C0. */
function stepOf(midi: number): number {
  const octave = Math.floor(midi / 12)
  return octave * 7 + STEP_OF_PITCH_CLASS[((midi % 12) + 12) % 12]
}

function useFlatNames(_pitchClass: number): boolean {
  // Sharps throughout: choosing per key would need the key here, and a
  // transcription that mixes both spellings reads worse than one that commits.
  return false
}

/** Half-space offsets needing a ledger line, for a note above or below the staff. */
function ledgerLines(offset: number): number[] {
  const lines: number[] = []
  for (let step = -2; step >= offset - 1; step -= 2) lines.push(step)
  for (let step = 10; step <= offset + 1; step += 2) lines.push(step)
  return lines
}
