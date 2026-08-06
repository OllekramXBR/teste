import { Link } from 'react-router-dom'

import type { JobStatus, Song, Stem } from '../lib/api'

interface Props {
  song: Song
  stems: Stem[]
  busy: string | null
  onTranscribe: () => void
  onSeparate: () => void
}

const LYRIC_LABELS: Record<JobStatus, string> = {
  none: 'Não transcrita',
  pending: 'Na fila…',
  transcribing: 'Ouvindo a voz…',
  separating: 'Separando…',
  ready: 'Pronta',
  failed: 'Falhou',
}

/**
 * The two long jobs, and the door to the stage.
 *
 * Both are opt-in. Chord detection costs seconds; recognising sung words costs
 * minutes and separating the stems costs several more, so neither runs on
 * upload — the user asks for them when they want them, and the card is honest
 * about the wait rather than showing a spinner that implies otherwise.
 */
export function ProductionCard({ song, stems, busy, onTranscribe, onSeparate }: Props) {
  const canPerform = stems.length > 0 && song.lyricsStatus === 'ready'

  return (
    <section className="rounded-xl border border-slate-200 bg-panel p-4 dark:border-slate-800">
      <h3 className="mb-3 text-sm font-semibold tracking-tight">Produção</h3>

      <Row
        title="Letra"
        status={LYRIC_LABELS[song.lyricsStatus] ?? song.lyricsStatus}
        tone={song.lyricsStatus}
        detail={
          song.lyricsStatus === 'ready' && song.lyrics
            ? `${song.lyrics.wordCount} palavras · ${song.lyrics.model}`
            : song.lyricsError
        }
        action={song.lyricsStatus === 'ready' ? 'Refazer' : 'Transcrever'}
        hint="Alguns minutos. Melhora muito depois de separar as pistas."
        busy={busy === 'lyrics'}
        onClick={onTranscribe}
      />

      <Row
        title="Pistas"
        status={stems.length ? `${stems.length} pistas` : (LYRIC_LABELS[song.stemsStatus] ?? '—')}
        tone={song.stemsStatus}
        detail={song.stemsError ?? (stems.length ? stems.map((s) => s.label).join(', ') : null)}
        action={stems.length ? 'Refazer' : 'Separar'}
        hint="Vários minutos. Separa a voz principal dos backing vocals e da banda."
        busy={busy === 'stems'}
        onClick={onSeparate}
      />

      <Link
        to={`/song/${song.id}/perform`}
        aria-disabled={!canPerform}
        onClick={(event) => {
          if (!canPerform) event.preventDefault()
        }}
        className={[
          'mt-4 flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition',
          canPerform
            ? 'bg-slate-900 text-white hover:bg-slate-700 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200'
            : 'cursor-not-allowed bg-slate-200 text-slate-400 dark:bg-slate-800 dark:text-slate-600',
        ].join(' ')}
      >
        Modo palco
      </Link>
      {!canPerform && (
        <p className="mt-1.5 text-center text-[11px] text-slate-400">
          Precisa da letra transcrita e das pistas separadas.
        </p>
      )}
    </section>
  )
}

function Row({
  title,
  status,
  tone,
  detail,
  action,
  hint,
  busy,
  onClick,
}: {
  title: string
  status: string
  tone: JobStatus
  detail?: string | null
  action: string
  hint: string
  busy: boolean
  onClick: () => void
}) {
  const running = tone === 'pending' || tone === 'transcribing' || tone === 'separating' || busy
  return (
    <div className="border-t border-slate-100 py-3 first:border-t-0 first:pt-0 dark:border-slate-800">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium">{title}</p>
          <p
            className={[
              'truncate text-xs',
              tone === 'failed' ? 'text-rose-500' : 'text-slate-500',
            ].join(' ')}
          >
            {status}
          </p>
        </div>
        <button
          type="button"
          onClick={onClick}
          disabled={running}
          title={hint}
          className="shrink-0 rounded-full border border-slate-300 px-3 py-1 text-xs font-medium transition hover:border-accent hover:text-accent disabled:opacity-40 dark:border-slate-700"
        >
          {running ? '…' : action}
        </button>
      </div>
      {detail && <p className="mt-1 truncate text-[11px] text-slate-400">{detail}</p>}
    </div>
  )
}
