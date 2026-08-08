import type { BeatEvent } from '../lib/api'

interface TransportProps {
  playing: boolean
  currentTime: number
  duration: number
  beats: BeatEvent[]
  loopRegion: { start: number; end: number } | null
  onToggle: () => void
  onSeek: (time: number) => void
}

export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00'
  const minutes = Math.floor(seconds / 60)
  const rest = Math.floor(seconds % 60)
  return `${minutes}:${rest.toString().padStart(2, '0')}`
}

/** Play/pause plus a scrub bar with bar markers and the loop region shaded. */
export function Transport({
  playing,
  currentTime,
  duration,
  beats,
  loopRegion,
  onToggle,
  onSeek,
}: TransportProps) {
  const progress = duration > 0 ? (currentTime / duration) * 100 : 0
  const downbeats = beats.filter((beat) => beat.downbeat)

  const handleScrub = (event: React.MouseEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    const fraction = (event.clientX - box.left) / box.width
    onSeek(Math.max(0, Math.min(1, fraction)) * duration)
  }

  return (
    <div className="flex items-center gap-4">
      <button
        type="button"
        onClick={onToggle}
        aria-label={playing ? 'Pausar' : 'Tocar'}
        className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-accent text-white shadow-lg transition hover:opacity-90 active:scale-95"
      >
        {playing ? (
          <svg width="18" height="18" viewBox="0 0 18 18" fill="currentColor">
            <rect x="2" y="1" width="5" height="16" rx="1" />
            <rect x="11" y="1" width="5" height="16" rx="1" />
          </svg>
        ) : (
          <svg width="18" height="18" viewBox="0 0 18 18" fill="currentColor">
            <path d="M3 1.5v15l13-7.5z" />
          </svg>
        )}
      </button>

      <span className="w-12 shrink-0 text-right text-xs tabular-nums text-ink-soft">
        {formatTime(currentTime)}
      </span>

      <div
        role="slider"
        tabIndex={0}
        aria-label="Posição na música"
        aria-valuemin={0}
        aria-valuemax={Math.round(duration)}
        aria-valuenow={Math.round(currentTime)}
        onClick={handleScrub}
        onKeyDown={(event) => {
          if (event.key === 'ArrowRight') onSeek(currentTime + 5)
          if (event.key === 'ArrowLeft') onSeek(currentTime - 5)
        }}
        className="relative h-8 flex-1 cursor-pointer overflow-hidden rounded-lg bg-canvas"
      >
        {loopRegion && duration > 0 && (
          <div
            className="absolute inset-y-0 bg-amber-300/50"
            style={{
              left: `${(loopRegion.start / duration) * 100}%`,
              width: `${((loopRegion.end - loopRegion.start) / duration) * 100}%`,
            }}
          />
        )}
        {duration > 0 &&
          downbeats.map((beat) => (
            <div
              key={beat.index}
              className="absolute inset-y-0 w-px bg-slate-400/40"
              style={{ left: `${(beat.time / duration) * 100}%` }}
            />
          ))}
        <div className="absolute inset-y-0 left-0 bg-indigo-500/40" style={{ width: `${progress}%` }} />
        <div
          className="absolute inset-y-0 w-0.5 bg-indigo-600"
          style={{ left: `${progress}%` }}
        />
      </div>

      <span className="w-12 shrink-0 text-xs tabular-nums text-ink-soft">
        {formatTime(duration)}
      </span>
    </div>
  )
}
