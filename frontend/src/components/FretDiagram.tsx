import { useMemo } from 'react'
import type { Instrument } from '../lib/fretboard'
import { getFingerings } from '../lib/fretboard'
import { intervalNames, mod12, noteName } from '../lib/theory'

interface FretDiagramProps {
  root: number
  quality: string
  instrument: Instrument
  useFlats?: boolean
  /** Which of the ranked fingerings to draw. */
  variant?: number
  width?: number
}

const FRET_COUNT = 5

/** A chord box for guitar or ukulele, drawn from a generated fingering. */
export function FretDiagram({
  root,
  quality,
  instrument,
  useFlats = false,
  variant = 0,
  width = 132,
}: FretDiagramProps) {
  const fingerings = useMemo(
    () => getFingerings(root, quality, instrument, 4),
    [root, quality, instrument],
  )
  const fingering = fingerings[Math.min(variant, Math.max(fingerings.length - 1, 0))]

  if (!fingering) {
    return (
      <div className="flex h-32 items-center justify-center text-xs text-slate-500">
        No playable shape
      </div>
    )
  }

  const stringCount = instrument.tuning.length
  const padding = { top: 26, right: 14, bottom: 20, left: 22 }
  const boardWidth = width - padding.left - padding.right
  const stringGap = boardWidth / (stringCount - 1)
  const fretGap = 22
  const height = padding.top + fretGap * FRET_COUNT + padding.bottom

  const frettedFrets = fingering.frets.filter((fret) => fret > 0)
  const lowest = frettedFrets.length ? Math.min(...frettedFrets) : 1
  // Show the nut whenever the shape sits in first position, otherwise slide the
  // window up the neck and label the starting fret.
  const startFret = lowest <= FRET_COUNT - 1 ? 1 : lowest
  const showNut = startFret === 1

  const x = (stringIndex: number) => padding.left + stringIndex * stringGap
  const y = (fretOffset: number) => padding.top + fretOffset * fretGap

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`${noteName(root, useFlats)}${quality} on ${instrument.name}`}
      className="select-none"
    >
      {showNut && (
        <rect
          x={padding.left - 1}
          y={padding.top - 4}
          width={boardWidth + 2}
          height={4}
          rx={1}
          className="fill-slate-300 dark:fill-slate-500"
        />
      )}
      {!showNut && (
        <text
          x={padding.left - 8}
          y={y(0.65)}
          textAnchor="end"
          className="fill-slate-400 text-[9px] font-medium"
        >
          {startFret}
        </text>
      )}

      {Array.from({ length: FRET_COUNT + 1 }, (_, index) => (
        <line
          key={`fret-${index}`}
          x1={padding.left}
          y1={y(index)}
          x2={padding.left + boardWidth}
          y2={y(index)}
          className="stroke-slate-300 dark:stroke-slate-600"
          strokeWidth={1}
        />
      ))}
      {Array.from({ length: stringCount }, (_, index) => (
        <line
          key={`string-${index}`}
          x1={x(index)}
          y1={y(0)}
          x2={x(index)}
          y2={y(FRET_COUNT)}
          className="stroke-slate-300 dark:stroke-slate-600"
          strokeWidth={1}
        />
      ))}

      {fingering.barre > 0 && fingering.barre >= startFret && (
        <rect
          x={x(0) - 5}
          y={y(fingering.barre - startFret + 0.5) - 6}
          width={boardWidth + 10}
          height={12}
          rx={6}
          className="fill-indigo-500/90"
        />
      )}

      {fingering.frets.map((fret, stringIndex) => {
        const cx = x(stringIndex)
        if (fret < 0) {
          return (
            <g key={`mark-${stringIndex}`} className="stroke-slate-400" strokeWidth={1.5}>
              <line x1={cx - 4} y1={padding.top - 16} x2={cx + 4} y2={padding.top - 8} />
              <line x1={cx - 4} y1={padding.top - 8} x2={cx + 4} y2={padding.top - 16} />
            </g>
          )
        }
        if (fret === 0) {
          return (
            <circle
              key={`mark-${stringIndex}`}
              cx={cx}
              cy={padding.top - 12}
              r={4}
              className="fill-none stroke-slate-400"
              strokeWidth={1.5}
            />
          )
        }
        const offset = fret - startFret + 0.5
        if (offset < 0 || offset > FRET_COUNT) return null
        const isRoot = mod12(instrument.tuning[stringIndex] + fret) === mod12(root)
        return (
          <circle
            key={`mark-${stringIndex}`}
            cx={cx}
            cy={y(offset)}
            r={6}
            className={isRoot ? 'fill-amber-400' : 'fill-indigo-500'}
          />
        )
      })}

      {instrument.stringNames.map((name, index) => (
        <text
          key={`name-${index}`}
          x={x(index)}
          y={height - 6}
          textAnchor="middle"
          className="fill-slate-400 text-[9px]"
        >
          {name}
        </text>
      ))}
    </svg>
  )
}

/** Legend describing what the coloured dots mean. */
export function ChordToneLegend({ quality }: { quality: string }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
      <span className="flex items-center gap-1">
        <span className="inline-block h-2.5 w-2.5 rounded-full bg-amber-400" /> root
      </span>
      <span className="flex items-center gap-1">
        <span className="inline-block h-2.5 w-2.5 rounded-full bg-indigo-500" /> chord tone
      </span>
      <span className="text-slate-400">{intervalNames(quality).join(' · ')}</span>
    </div>
  )
}
