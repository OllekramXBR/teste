import type { Bar } from './ChordGrid'

interface Section {
  name: string
  start: number
}

interface Props {
  sections: Section[]
  currentTime: number
  duration: number
  bars: Bar[]
  onSeek: (time: number) => void
  onLoop: (startBar: number, endBar: number) => void
}

/**
 * The song's parts as buttons: Intro, Verso, Refrão.
 *
 * These names come from the imported chart's [markers], timed by the lyric
 * alignment — which means the app can finally speak the language a musician
 * rehearses in. Tap a part to jump there; tap its loop glyph to repeat it.
 * "Repetir o refrão" is the sentence every practice session actually says,
 * and it beats "repetir os compassos 17 a 24" every time.
 */
export function SectionRail({ sections, currentTime, duration, bars, onSeek, onLoop }: Props) {
  if (!sections.length) return null

  const barOf = (time: number): number | null => {
    for (const bar of bars) {
      if (time >= bar.start && time < bar.end) return bar.number
    }
    return bars.length ? bars[bars.length - 1].number : null
  }

  const endOf = (index: number) => sections[index + 1]?.start ?? duration

  const activeIndex = (() => {
    for (let index = sections.length - 1; index >= 0; index -= 1) {
      if (currentTime >= sections[index].start) return index
    }
    return -1
  })()

  return (
    <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5">
      <span className="shrink-0 text-[10px] font-bold uppercase tracking-[0.18em] text-ink-faint">
        Partes
      </span>
      {sections.map((section, index) => {
        const active = index === activeIndex
        return (
          <span
            key={`${section.start}-${index}`}
            className={[
              'flex shrink-0 items-stretch overflow-hidden rounded-full border text-xs font-semibold transition-all',
              active
                ? 'border-accent bg-accent-soft text-accent-ink'
                : 'border-line text-ink-soft hover:border-accent/60',
            ].join(' ')}
          >
            <button
              type="button"
              onClick={() => onSeek(section.start)}
              title={`Tocar a partir de ${section.name}`}
              className="px-3 py-1 transition hover:text-accent"
            >
              {section.name}
            </button>
            <button
              type="button"
              onClick={() => {
                const startBar = barOf(section.start)
                const endBar = barOf(Math.max(section.start, endOf(index) - 0.05))
                if (startBar !== null && endBar !== null) {
                  onLoop(startBar, Math.max(startBar, endBar))
                }
              }}
              title={`Repetir ${section.name} em loop`}
              aria-label={`Repetir ${section.name} em loop`}
              className="border-l border-line/60 px-2 py-1 text-ink-faint transition hover:bg-flame-soft hover:text-flame"
            >
              ↻
            </button>
          </span>
        )
      })}
    </div>
  )
}
