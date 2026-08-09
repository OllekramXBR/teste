import { useMemo, useState } from 'react'

import { br } from '../lib/brazilian'
import { getFingerings, INSTRUMENTS, type Instrument } from '../lib/fretboard'
import { mod12, noteName, parseLabel, transposeLabel } from '../lib/theory'
import { loadVocalRange, VocalRange, type VocalRangeValue } from './VocalRange'

interface Props {
  uniqueChords: string[]
  keyTonic: number
  keyMode: string
  useFlats: boolean
  instrument: Instrument['id']
  transpose: number
  /** MIDI numbers of the song's melody, for judging keys against a voice. */
  melodyMidi?: number[]
  onTranspose: (semitones: number) => void
  /** Null when the song has no stems, so the audio cannot follow. */
  onRenderAudio?: (semitones: number) => void
  renderedKeys?: Set<number>
  /** Render just the list, for a host that already provides card and title. */
  frameless?: boolean
}

/** How far a song can move before it stops being the same song to sing. */
const RANGE = [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6]

/**
 * The melody's working range, by percentile rather than min/max: a single
 * shriek from the pitch tracker must not define the song. The melody comes
 * from the mix's dominant voice, which on a sung recording is the singer —
 * the same bias the tablature complains about, put to work here.
 */
function melodyBand(midi: number[]): { low: number; high: number } | null {
  if (midi.length < 8) return null
  const sorted = [...midi].sort((a, b) => a - b)
  const at = (fraction: number) => sorted[Math.floor(fraction * (sorted.length - 1))]
  return { low: at(0.1), high: at(0.9) }
}

type Fit =
  | { kind: 'fits' }
  | { kind: 'high'; by: number }
  | { kind: 'low'; by: number }

function judge(band: { low: number; high: number }, voice: VocalRangeValue, shift: number): Fit {
  // No free octave: the melody's octave belongs to the song, and giving the
  // judge octave freedom made every key "fit" — a verdict that is always yes
  // is not a verdict. A singer who habitually drops an octave already knows
  // they do, and reads "▲3" as "▲3 for the original octave".
  const low = band.low + shift
  const high = band.high + shift
  const over = Math.max(0, high - voice.high)
  const under = Math.max(0, voice.low - low)
  if (over === 0 && under === 0) return { kind: 'fits' }
  return over >= under ? { kind: 'high', by: over } : { kind: 'low', by: under }
}

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
  melodyMidi,
  onTranspose,
  onRenderAudio,
  renderedKeys,
  frameless = false,
}: Props) {
  const [voice, setVoice] = useState<VocalRangeValue | null>(loadVocalRange)
  const band = useMemo(() => (melodyMidi ? melodyBand(melodyMidi) : null), [melodyMidi])

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
        fit: band && voice ? judge(band, voice, semitones) : null,
      }
    })
  }, [uniqueChords, keyTonic, keyMode, useFlats, instrument, band, voice])

  const easiest = useMemo(
    () => rows.reduce((best, row) => (row.open > best.open ? row : best), rows[0]),
    [rows],
  )

  const body = (
    <>
      <p className="mb-2 text-xs text-ink-soft">
        Mova até caber na sua voz. O número conta quantos acordes saem sem pestana, no{' '}
        {(INSTRUMENTS[instrument] ?? INSTRUMENTS.guitar).name.toLowerCase()}.
      </p>

      <div className="mb-3">
        <VocalRange value={voice} onChange={setVoice} />
        {voice && !band && (
          <p className="mt-1.5 text-[11px] text-ink-faint">
            Ainda não conheço a melodia desta música o suficiente para comparar com a sua voz.
          </p>
        )}
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
                    {row.fit && (
                      <span
                        className={[
                          'shrink-0 rounded-full px-1.5 text-[10px] font-semibold',
                          row.fit.kind === 'fits'
                            ? 'bg-flame-soft text-flame'
                            : row.fit.kind === 'high'
                              ? 'text-rose-500'
                              : 'text-sky-500',
                        ].join(' ')}
                        title={
                          row.fit.kind === 'fits'
                            ? 'A melodia cabe na sua voz neste tom'
                            : row.fit.kind === 'high'
                              ? `Sobe ${row.fit.by} semitons acima do seu agudo`
                              : `Desce ${row.fit.by} semitons abaixo do seu grave`
                        }
                      >
                        {row.fit.kind === 'fits'
                          ? 'na voz'
                          : row.fit.kind === 'high'
                            ? `▲${row.fit.by}`
                            : `▼${row.fit.by}`}
                      </span>
                    )}
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
    </>
  )

  if (frameless) return <div>{body}</div>

  return (
    <section className="rounded-xl border border-line bg-panel p-4">
      <h3 className="mb-2 text-sm font-semibold tracking-tight">Em que tom cantar</h3>
      {body}
    </section>
  )
}
