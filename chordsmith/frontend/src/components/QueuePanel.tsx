import { useCallback, useEffect, useState } from 'react'

import { elapsedLabel } from '../hooks/useJobProgress'
import * as api from '../lib/api'
import type { RunningJob, Song } from '../lib/api'

const KIND_LABELS: Record<string, string> = {
  stems: 'Separando pistas',
  lyrics: 'Transcrevendo a letra',
  tracks: 'Lendo as notas de cada pista',
  variant: 'Rendendo tom e andamento',
}

interface Props {
  songs: Song[]
  onQueued: () => void
}

/**
 * What the machine is doing right now, and how much is left.
 *
 * The library used to say nothing at all about the queue, which is why work
 * that takes half an hour per song felt like work that was not happening. This
 * is deliberately about the *library*, not one song: with seventy recordings
 * waiting, the question is not "how is this one going" but "how long until I
 * can stop watching".
 */
export function QueuePanel({ songs, onQueued }: Props) {
  const [running, setRunning] = useState<RunningJob[]>([])
  const [queued, setQueued] = useState<Record<string, number>>({})
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  const failed = songs.filter(
    (song) => song.stemsStatus === 'failed' || song.lyricsStatus === 'failed',
  ).length
  const active = running.length > 0 || Object.keys(queued).length > 0

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    const poll = async () => {
      try {
        const snapshot = await api.getLibraryProgress()
        if (cancelled) return
        setRunning(snapshot.running)
        setQueued(snapshot.queued as Record<string, number>)
      } catch {
        // Nothing to show is the honest response to not being able to ask.
      }
      // Slower than the per-song bar: this is a summary, and a summary that
      // costs a request every second and a half all day is not worth it.
      if (!cancelled) timer = window.setTimeout(poll, 4000)
    }

    void poll()
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [])

  const retry = useCallback(async () => {
    setBusy(true)
    setNote(null)
    try {
      // 'fast' by name rather than by relying on the server default: a person
      // clicking this is choosing to wait hours, and which number of hours it
      // is should not depend on an environment variable they cannot see.
      const result = await api.retryFailed('both', 'fast')
      const total = result.lyrics + result.stems
      setNote(
        total === 0
          ? 'Nada pendente para refazer.'
          : `Na fila: ${result.stems} separações e ${result.lyrics} letras.`,
      )
      onQueued()
    } catch (error) {
      setNote(error instanceof Error ? error.message : 'Não consegui falar com o servidor.')
    } finally {
      setBusy(false)
    }
  }, [onQueued])

  if (!active && failed === 0) return null

  const waiting = Object.entries(queued).reduce((sum, [, count]) => sum + count, 0)

  return (
    <section className="rounded-xl border border-line bg-panel p-4">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold tracking-tight">Fila</h3>
        {waiting > 0 && (
          <span className="text-xs text-ink-faint">
            {waiting} {waiting === 1 ? 'esperando' : 'esperando'}
          </span>
        )}
      </div>

      {running.map((job) => (
        <JobLine key={`${job.kind}:${job.songId}`} job={job} songs={songs} />
      ))}

      {!active && failed > 0 && (
        <p className="mt-2 text-xs text-ink-soft">
          {failed} {failed === 1 ? 'música parou' : 'músicas pararam'} no meio. Quase sempre é
          trabalho interrompido, não música que o modelo não dá conta.
        </p>
      )}

      {failed > 0 && (
        <button
          type="button"
          onClick={retry}
          disabled={busy}
          className="mt-3 w-full rounded-lg border border-line px-4 py-2 text-xs font-medium transition hover:border-accent hover:text-accent disabled:opacity-40"
        >
          {busy ? 'Enfileirando…' : `Refazer as que falharam (${failed})`}
        </button>
      )}
      {note && <p className="mt-2 text-center text-[11px] text-ink-faint">{note}</p>}
    </section>
  )
}

function JobLine({ job, songs }: { job: RunningJob; songs: Song[] }) {
  const song = songs.find((candidate) => candidate.id === job.songId)
  const percent = job.overall === null ? null : Math.round(job.overall * 100)

  return (
    <div className="mt-3">
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span className="truncate font-medium">{song?.title ?? job.songId}</span>
        <span className="shrink-0 tabular-nums text-ink-faint">
          {percent !== null && `${percent}% · `}
          há {elapsedLabel(job.elapsedSeconds)}
        </span>
      </div>
      <p className="truncate text-[11px] text-ink-faint">
        {KIND_LABELS[job.kind] ?? job.kind}
        {job.stage && ` — ${job.stage}`}
        {job.steps > 1 && ` (${job.step}/${job.steps})`}
      </p>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-canvas">
        {percent === null ? (
          <div className="h-full w-1/3 animate-[slide_1.4s_ease-in-out_infinite] rounded-full bg-accent/60" />
        ) : (
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-700 ease-out"
            style={{ width: `${Math.max(percent, 2)}%` }}
          />
        )}
      </div>
    </div>
  )
}
