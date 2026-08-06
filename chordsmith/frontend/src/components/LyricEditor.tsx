import { useEffect, useMemo, useState } from 'react'

import type { Lyrics, LyricSegment } from '../lib/api'

interface Props {
  lyrics: Lyrics
  currentTime: number
  saving: boolean
  onSave: (segments: LyricSegment[]) => void
  onCancel: () => void
  onSeek?: (time: number) => void
}

/**
 * Correcting a transcription, one line at a time.
 *
 * Per line rather than per word, because that is the shape the mistakes come
 * in: the recogniser hears one wrong word inside a phrase it otherwise got
 * right. Asking someone to fix that word by word — each with its own start and
 * end in seconds — would be more work than the mistake is worth.
 *
 * The timestamps are shown but not editable. They came from the recording and
 * are almost always right; what is wrong is the words. A line can be played on
 * its own, which is the only reliable way to check a lyric against what was
 * actually sung.
 */
export function LyricEditor({ lyrics, currentTime, saving, onSave, onCancel, onSeek }: Props) {
  const [lines, setLines] = useState<LyricSegment[]>(() => lyrics.segments.map((line) => ({ ...line })))

  useEffect(() => {
    setLines(lyrics.segments.map((line) => ({ ...line })))
  }, [lyrics])

  const dirty = useMemo(
    () => lines.some((line, index) => line.text !== lyrics.segments[index]?.text),
    [lines, lyrics.segments],
  )

  const update = (index: number, text: string) => {
    setLines((previous) =>
      previous.map((line, position) => (position === index ? { ...line, text } : line)),
    )
  }

  return (
    <div className="rounded-xl border border-line bg-panel ">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3 ">
        <p className="text-sm">
          <span className="font-semibold">Corrigindo a letra</span>
          <span className="ml-2 text-xs text-ink-soft">
            {lines.length} linhas · clique no tempo para ouvir a linha
          </span>
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-full border border-line px-4 py-1.5 text-xs font-medium "
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => onSave(lines)}
            disabled={!dirty || saving}
            className="rounded-full bg-ink px-4 py-1.5 text-xs font-semibold text-canvas disabled:opacity-40"
          >
            {saving ? 'Salvando…' : 'Salvar'}
          </button>
        </div>
      </div>

      <ul className="max-h-[30rem] divide-y divide-line overflow-y-auto ">
        {lines.map((line, index) => {
          const playing = currentTime >= line.start && currentTime < line.end
          return (
            <li
              key={`${line.start}-${index}`}
              className={playing ? 'bg-accent-soft' : undefined}
            >
              <div className="flex items-start gap-3 px-4 py-2">
                <button
                  type="button"
                  onClick={() => onSeek?.(line.start)}
                  className="mt-1.5 w-14 shrink-0 text-left text-[11px] tabular-nums text-ink-faint hover:text-accent"
                  title="Ouvir esta linha"
                >
                  {formatTime(line.start)}
                </button>
                <input
                  value={line.text}
                  onChange={(event) => update(index, event.target.value)}
                  className="w-full rounded-md border border-transparent bg-transparent px-2 py-1 text-sm focus:border-accent focus:outline-none"
                  aria-label={`Linha em ${formatTime(line.start)}`}
                />
              </div>
            </li>
          )
        })}
      </ul>

      <p className="border-t border-line px-4 py-2.5 text-[11px] text-ink-faint ">
        Ao salvar, o tempo de cada palavra é redistribuído dentro da linha. A letra passa a contar
        como corrigida, e transcrever de novo não apaga o que você escreveu sem avisar.
      </p>
    </div>
  )
}

function formatTime(seconds: number): string {
  const whole = Math.floor(seconds)
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`
}
