import { mod12, noteName } from '../lib/theory'

interface PianoDiagramProps {
  root: number
  notes: number[]
  useFlats?: boolean
  octaves?: number
  width?: number
}

// Semitone offsets of the white keys within an octave, and of the black keys
// with the white-key index they sit between.
const WHITE_OFFSETS = [0, 2, 4, 5, 7, 9, 11]
const BLACK_KEYS = [
  { offset: 1, after: 0 },
  { offset: 3, after: 1 },
  { offset: 6, after: 3 },
  { offset: 8, after: 4 },
  { offset: 10, after: 5 },
]

/** Keyboard showing which pitch classes belong to the chord. */
export function PianoDiagram({
  root,
  notes,
  useFlats = false,
  octaves = 2,
  width = 200,
}: PianoDiagramProps) {
  const highlighted = new Set(notes.map(mod12))
  const whiteCount = WHITE_OFFSETS.length * octaves
  const whiteWidth = width / whiteCount
  const height = whiteWidth * 4.2
  const blackWidth = whiteWidth * 0.62
  const blackHeight = height * 0.62

  const keyClass = (pitchClass: number, black: boolean) => {
    if (mod12(pitchClass) === mod12(root)) return 'fill-amber-400'
    if (highlighted.has(mod12(pitchClass))) return 'fill-indigo-500'
    return black ? 'fill-slate-800 dark:fill-slate-900' : 'fill-white dark:fill-slate-200'
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Acorde de ${noteName(root, useFlats)} no teclado`}
      className="select-none"
    >
      {Array.from({ length: octaves }, (_, octave) =>
        WHITE_OFFSETS.map((offset, index) => {
          const keyIndex = octave * WHITE_OFFSETS.length + index
          const pitchClass = mod12(root + offset)
          return (
            <rect
              key={`white-${keyIndex}`}
              x={keyIndex * whiteWidth}
              y={0}
              width={whiteWidth - 1}
              height={height}
              rx={2}
              className={`${keyClass(pitchClass, false)} stroke-slate-300 dark:stroke-slate-600`}
              strokeWidth={1}
            />
          )
        }),
      )}
      {Array.from({ length: octaves }, (_, octave) =>
        BLACK_KEYS.map(({ offset, after }) => {
          const keyIndex = octave * WHITE_OFFSETS.length + after
          const pitchClass = mod12(root + offset)
          return (
            <rect
              key={`black-${octave}-${offset}`}
              x={(keyIndex + 1) * whiteWidth - blackWidth / 2 - 0.5}
              y={0}
              width={blackWidth}
              height={blackHeight}
              rx={2}
              className={keyClass(pitchClass, true)}
            />
          )
        }),
      )}
    </svg>
  )
}
