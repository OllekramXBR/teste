import type { Analysis } from '../lib/api'
import { displayLabel, groupIntoBars } from './ChordGrid'

interface ChordSheetProps {
  title: string
  artist: string
  analysis: Analysis
  transpose: number
  capo: number
}

/**
 * Printable chord sheet. Hidden on screen and revealed by the print
 * stylesheet, so "Download PDF" is just the browser's own print-to-PDF.
 */
export function ChordSheet({ title, artist, analysis, transpose, capo }: ChordSheetProps) {
  const bars = groupIntoBars(analysis.beats)
  const useFlats = analysis.useFlats

  return (
    <div className="chord-sheet hidden print:block">
      <h1 className="text-2xl font-bold">{title}</h1>
      {artist && <p className="text-sm text-ink-soft">{artist}</p>}
      <p className="mt-1 text-xs text-ink-soft">
        {analysis.key.name}
        {transpose !== 0 && ` · transposed ${transpose > 0 ? '+' : ''}${transpose}`}
        {capo > 0 && ` · capo fret ${capo}`} · {Math.round(analysis.bpm)} BPM ·{' '}
        {analysis.beatsPerBar}/4
      </p>

      <div className="mt-4 grid grid-cols-4 gap-x-4 gap-y-2">
        {bars.map((bar) => {
          const labels: string[] = []
          for (const beat of bar.beats) {
            const label = displayLabel(beat.label, transpose, capo, useFlats)
            if (!labels.length || labels[labels.length - 1] !== label) labels.push(label)
          }
          return (
            <div key={bar.number} className="border-b border-line pb-1">
              <div className="text-[8px] text-ink-faint">{bar.number}</div>
              <div className="text-sm font-semibold">
                {labels.filter(Boolean).join('  ') || '–'}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
