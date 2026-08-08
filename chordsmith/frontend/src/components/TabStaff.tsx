import { useEffect, useMemo, useRef } from 'react'
import type { Lead, LeadNote } from '../lib/api'
import type { Bar } from './ChordGrid'

interface TabStaffProps {
  lead: Lead
  bars: Bar[]
  currentTime: number
  onSeek: (time: number) => void
  autoScroll: boolean
}

const STRING_GAP = 13
const BAR_MIN_WIDTH = 190
const TOP_PADDING = 10

interface BarNotes {
  bar: Bar
  notes: LeadNote[]
  isSolo: boolean
}

/**
 * Guitar tablature for the transcribed lead line.
 *
 * Notes are positioned by their real onset time within the bar rather than
 * quantised to a rhythmic grid, so what you read lines up with what you hear
 * even when the playing is loose.
 */
export function TabStaff({ lead, bars, currentTime, onSeek, autoScroll }: TabStaffProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const activeRef = useRef<HTMLDivElement | null>(null)
  const stringCount = lead.stringNames.length
  const staffHeight = TOP_PADDING * 2 + (stringCount - 1) * STRING_GAP

  const barNotes = useMemo<BarNotes[]>(() => {
    const soloBars = new Set<number>()
    for (const section of lead.sections) {
      if (!section.isSolo) continue
      for (let bar = section.startBar; bar <= section.endBar; bar += 1) soloBars.add(bar)
    }
    const byBar = new Map<number, LeadNote[]>()
    for (const note of lead.notes) {
      const existing = byBar.get(note.bar)
      if (existing) existing.push(note)
      else byBar.set(note.bar, [note])
    }
    return bars
      .map((bar) => ({
        bar,
        notes: byBar.get(bar.number) ?? [],
        isSolo: soloBars.has(bar.number),
      }))
      .filter((entry) => entry.notes.length > 0)
  }, [lead, bars])

  const activeBarNumber = useMemo(() => {
    const active = barNotes.find(
      (entry) => currentTime >= entry.bar.start && currentTime < entry.bar.end,
    )
    return active?.bar.number ?? -1
  }, [barNotes, currentTime])

  useEffect(() => {
    if (!autoScroll || !activeRef.current || !containerRef.current) return
    const container = containerRef.current
    const box = container.getBoundingClientRect()
    const element = activeRef.current.getBoundingClientRect()
    if (element.top < box.top + 20 || element.bottom > box.bottom - 20) {
      container.scrollTo({
        top: container.scrollTop + (element.top - box.top) - box.height / 3,
        behavior: 'smooth',
      })
    }
  }, [activeBarNumber, autoScroll])

  if (!barNotes.length) {
    return (
      <div className="rounded-xl bg-canvas p-8 text-center text-sm text-ink-soft">
        No lead line was picked out of this track. Transcription follows the loudest melodic voice,
        so tracks that are all rhythm parts — or where the melody is buried — come back empty.
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className="max-h-[58vh] overflow-y-auto rounded-xl bg-canvas p-3"
    >
      <div
        className="grid gap-3"
        style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${BAR_MIN_WIDTH}px, 1fr))` }}
      >
        {barNotes.map(({ bar, notes, isSolo }) => {
          const isActive = bar.number === activeBarNumber
          const span = Math.max(bar.end - bar.start, 0.001)
          return (
            <div
              key={bar.number}
              ref={isActive ? activeRef : undefined}
              className={[
                'relative rounded-lg border p-2 transition-colors',
                isActive
                  ? 'border-accent bg-accent-soft'
                  : 'border-line bg-panel',
                isSolo ? 'ring-2 ring-fuchsia-400/70' : '',
              ].join(' ')}
            >
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[9px] font-semibold text-ink-faint">{bar.number}</span>
                {isSolo && (
                  <span className="rounded bg-flame px-1 text-[8px] font-bold uppercase text-canvas">
                    solo
                  </span>
                )}
              </div>

              <div className="flex gap-1">
                {/* String names down the left edge, high string on top, the way
                    tab is conventionally written. */}
                <div className="relative w-3 shrink-0" style={{ height: staffHeight }}>
                  {lead.stringNames
                    .slice()
                    .reverse()
                    .map((name, index) => (
                      <span
                        key={name + index}
                        className="absolute text-[8px] leading-none text-ink-faint"
                        style={{ top: TOP_PADDING + index * STRING_GAP - 3 }}
                      >
                        {name}
                      </span>
                    ))}
                </div>

                <div className="relative flex-1" style={{ height: staffHeight }}>
                  <svg
                    width="100%"
                    height={staffHeight}
                    viewBox={`0 0 100 ${staffHeight}`}
                    preserveAspectRatio="none"
                    role="img"
                    aria-label={`Tablature for bar ${bar.number}`}
                    className="absolute inset-0"
                  >
                    {lead.stringNames.map((_, index) => (
                      <line
                        key={index}
                        x1={0}
                        x2={100}
                        y1={TOP_PADDING + index * STRING_GAP}
                        y2={TOP_PADDING + index * STRING_GAP}
                        className="stroke-slate-300 dark:stroke-slate-600"
                        strokeWidth={0.4}
                        vectorEffect="non-scaling-stroke"
                      />
                    ))}
                  </svg>

                  {/* Fret numbers live outside the SVG so the stretched viewBox
                      cannot distort their glyphs. */}
                  {notes.map((note) => {
                    if (note.string === null || note.fret === null) return null
                    const left = ((note.start - bar.start) / span) * 100
                    const sounding = currentTime >= note.start && currentTime < note.end
                    // String 0 is the lowest-pitched string, drawn at the bottom.
                    const row = stringCount - 1 - note.string
                    return (
                      <button
                        key={`${note.start}-${note.midi}`}
                        type="button"
                        onClick={() => onSeek(note.start)}
                        title={`${note.name} — string ${lead.stringNames[note.string]}, fret ${
                          note.fret
                        }`}
                        className={`absolute -translate-x-1/2 -translate-y-1/2 rounded px-0.5 text-[10px] font-bold leading-tight tabular-nums ${
                          sounding
                            ? 'z-10 bg-accent text-canvas'
                            : 'bg-canvas text-ink'
                        }`}
                        style={{
                          left: `${Math.min(Math.max(left, 2), 96)}%`,
                          top: TOP_PADDING + row * STRING_GAP,
                        }}
                      >
                        {note.fret}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** Summary strip listing the detected lead sections and which read as solos. */
export function LeadSummary({
  lead,
  onSeek,
}: {
  lead: Lead
  onSeek: (time: number) => void
}) {
  if (!lead.sections.length) return null
  const solos = lead.sections.filter((section) => section.isSolo)

  return (
    <div className="rounded-xl border border-line bg-panel p-3">
      <h3 className="mb-2 text-sm font-semibold">
        Lead line — {lead.sections.length} section{lead.sections.length === 1 ? '' : 's'}
        {solos.length > 0 &&
          `, ${solos.length} of which ${solos.length === 1 ? 'reads' : 'read'} as a solo`}
      </h3>
      <div className="flex flex-wrap gap-1.5">
        {lead.sections.map((section) => (
          <button
            key={section.startBar}
            type="button"
            onClick={() => onSeek(section.start)}
            title={`${section.noteCount} notes, ${section.notesPerBar} per bar, ${section.lowName}–${section.highName}`}
            className={`rounded px-2 py-1 text-xs font-semibold transition-colors ${
              section.isSolo
                ? 'bg-flame text-canvas hover:brightness-110'
                : 'bg-canvas text-ink-soft hover:bg-accent-soft'
            }`}
          >
            bars {section.startBar}–{section.endBar}
            <span className="ml-1 font-normal opacity-80">
              {section.lowName}–{section.highName}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
