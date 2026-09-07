import { useEffect, useState } from 'react'

import * as api from '../lib/api'
import type { RunningJob, SongProgress } from '../lib/api'

const EMPTY: SongProgress = { running: [], waiting: {} }

/**
 * How far along this song's long jobs are.
 *
 * Polled apart from the song itself, and faster: the song is checked every few
 * seconds because its status rarely changes, while a bar that only moves at
 * that rate looks stuck. Nothing is polled at all when no job is running, so an
 * idle library page makes no requests.
 */
export function useJobProgress(songId: string | null, active: boolean): SongProgress {
  const [progress, setProgress] = useState<SongProgress>(EMPTY)

  useEffect(() => {
    if (!songId || !active) {
      setProgress(EMPTY)
      return
    }
    let cancelled = false
    let timer: number | undefined

    const poll = async () => {
      try {
        const fetched = await api.getSongProgress(songId)
        if (cancelled) return
        setProgress(fetched)
      } catch {
        // A failed poll is not worth showing: the bar simply does not move, and
        // the next attempt is a second and a half away.
      }
      if (!cancelled) timer = window.setTimeout(poll, 1500)
    }

    void poll()
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [songId, active])

  return progress
}

export function jobOf(progress: SongProgress, kind: RunningJob['kind']): RunningJob | null {
  return progress.running.find((job) => job.kind === kind) ?? null
}

/** "4 min" — coarse on purpose, because a seconds counter invites watching it. */
export function elapsedLabel(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  const minutes = Math.floor(seconds / 60)
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)}h${minutes % 60}`
}
