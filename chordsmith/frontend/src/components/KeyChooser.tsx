import { useMemo } from 'react'

import { br } from '../lib/brazilian'
import { getFingerings, INSTRUMENTS, type Instrument } from '../lib/fretboard'
import { mod12, noteName, parseLabel, transposeLabel } from '../lib/theory'

interface Props {
  uniqueChords: string[]
  keyTonic: number
  keyMode: string
  useFlats: boolean
  instrument: Instrument['id']
  transpose: number
  onTranspose: (semitones: number) => void
  /** Null when the song has no stems, so the audio cannot follow. */
  onRenderAudio?: (semitones: number) => void
  renderedKeys?: Set<number>
}

/** How far a song can move before it stops being the same song to sing. */
const RANGE = [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6]

/**
 * Which key to sing this in, and what it costs to play there.
 *
 * A singer picks a key by range, not by theory, and then has to live with
 * whatever shapes that key demands. So both are shown at once: move the song
 * until it sits in your voice, and see immediately whether you have just
 * committed to a page of barre chords.
 *
 * "Easy" here means an open position — nothing above the fourth fret and no
 * barre — counted with the same fretboard search that draws the diagrams, so
 * the number cannot disagree with the shapes.
 */
export function KeyChooser({
  uniqueChords,
  keyTonic,
  keyMode,
  useFlats,
  instrument,
  transpose,
  onTranspose,
  onRenderAudio,
  renderedKeys,
}: Props) {
  const rows = useMemo(() => {
    const board = INSTRUMENTS[instrument] ?? INSTRUMENTS.guitar
    return RANGE.map((semitones) => {
      const labels = uniqueChords.map((label) => transposeLabel(label, semitones, useFlats))
      let open = 0
      for (const label of labels) {
        const parsed = parseLabel(label)
        if (!parsed) continue
        const [best] = getFingerings(parsed.root, parsed.quality, board, 1)
        if (best && best.barre === 0 && best.baseFret <= 4) open += 1
      }
      return {
        semitones,
        key: `${noteName(mod12(keyTonic + semitones), useFlats)} ${keyMode === 'minor' ? 'menor' : 'maior'}`,
        labels: labels.map((label) => br(label, useFlats)),
        open,
        total: labels.length,
      }
    })
  }, [uniqueChords, keyTonic, keyMode, useFlats, instrument])

  const easiest = useMemo(
    () => rows.reduce((best, row) => (row.open > best.open ? row : best), rows[0]),
    [rows],
  )

  return (
    <section className="rounded-xl border border-line bg-panel p-4 ">
      <div className="mb-3">
        <h3 className="text-sm font-semibold tracking-tight">Em que tom cantar</h3>
        <p className="text-xs text-ink-soft">
          Mova até caber na sua voz. “Abertos” conta quantos acordes saem sem pestana, no{' '}
          {(INSTRUMENTS[instrument] ?? INSTRUMENTS.guitar).name.toLowerCase()}.
        </p>
      </div>

      <ul className="space-y-1">
        {rows.map((row) => {
          const active = row.semitones === transpose
          const rendered = renderedKeys?.has(row.semitones)
          return (
            <li key={row.semitones}>
              <div
                className={[
                  'flex items-start gap-2 rounded-lg px-2 py-1.5 transition',
                  active ? 'bg-accent-soft' : '',
                ].join(' ')}
              >
                <button
                  type="button"
                  onClick={() => onTranspose(row.semitones)}
                  className="min-w-0 flex-1 text-left"
                >
                  <span className="flex items-baseline gap-2">
                    <span className="w-7 shrink-0 text-xs tabular-nums text-ink-faint">
                      {row.semitones > 0 ? `+${row.semitones}` : row.semitones}
                    </span>
                    <span className="truncate text-sm font-medium">{row.key}</span>
                    <span
                      className={[
                        'ml-auto shrink-0 rounded-full px-1.5 text-[10px] font-semibold tabular-nums',
                        row.semitones === easiest.semitones
                          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'
                          : 'text-ink-faint',
                      ].join(' ')}
                      title="Acordes que saem em posição aberta"
                    >
                      {row.open}/{row.total}
                    </span>
                  </span>
                  {/* Second line: twenty chord labels never fitted beside a key
                      name in a 260px column, and squeezing them there is what
                      made the badge sit on top of the text. */}
                  <span className="mt-0.5 block truncate pl-9 font-mono text-[11px] text-ink-soft">
                    {row.labels.join(' ')}
                  </span>
                </button>

                {onRenderAudio && row.semitones !== 0 && (
                  <button
                    type="button"
                    onClick={() => onRenderAudio(row.semitones)}
                    disabled={rendered}
                    className="shrink-0 self-start rounded-full border border-line px-2 py-0.5 text-[10px] font-medium disabled:opacity-40"
                    title="Renderizar o áudio neste tom"
                  >
                    {rendered ? '✓' : 'áudio'}
                  </button>
                )}
              </div>
            </li>
          )
        })}
      </ul>

      {!onRenderAudio && (
        <p className="mt-3 text-[11px] text-ink-faint">
          Separe as pistas para poder ouvir a gravação no tom escolhido — sem elas a transposição
          muda só a grade.
        </p>
      )}
    </section>
  )
}
