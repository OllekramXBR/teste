import { useCallback, useEffect, useRef, useState } from 'react'

import * as api from '../lib/api'
import type { CifraclubResult, ChartComparison, WebChart } from '../lib/api'

interface Props {
  songId: string
}

const VERDICT_CLASS: Record<string, string> = {
  match: 'bg-emerald-500/15 text-emerald-700 border-emerald-500/40 dark:text-emerald-300',
  partial: 'bg-amber-500/15 text-amber-700 border-amber-500/40 dark:text-amber-300',
  diff: 'bg-rose-500/15 text-rose-700 border-rose-500/40 dark:text-rose-300',
  missing: 'bg-sky-500/15 text-sky-700 border-sky-500/40 dark:text-sky-300',
  noChord: 'bg-slate-500/15 text-slate-600 border-slate-400/40 dark:text-slate-400',
}

/**
 * The web chart attached to a song: find one on Cifra Club, import it, then
 * ask the backend how the written harmony and the heard harmony agree.
 *
 * A separate panel rather than a tab, because importing is a per-song decision
 * a reader makes once — search, pick, attach — and only then do they care
 * about the comparison marks. The chart is cached on the server, so opening
 * the panel again never re-fetches the site.
 */
export function WebChartPanel({ songId }: Props) {
  const [chart, setChart] = useState<WebChart | null>(null)
  const [chartMissing, setChartMissing] = useState(false)
  const [comparison, setComparison] = useState<ChartComparison | null>(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<CifraclubResult[]>([])
  const [searching, setSearching] = useState(false)
  const [searched, setSearched] = useState(false)
  const [importing, setImporting] = useState<number | null>(null)
  const [comparing, setComparing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const requestRef = useRef(0)

  useEffect(() => {
    const ticket = ++requestRef.current
    api
      .getWebChart(songId)
      .then((fetched) => {
        if (ticket !== requestRef.current) return
        setChart(fetched)
        setChartMissing(false)
      })
      .catch(() => {
        if (ticket !== requestRef.current) return
        setChart(null)
        setChartMissing(true)
      })
    return () => {
      requestRef.current += 1
    }
  }, [songId])

  const search = useCallback(async () => {
    if (!query.trim()) return
    setSearching(true)
    setError(null)
    const ticket = ++requestRef.current
    try {
      const response = await api.searchCifraclub(query)
      if (ticket !== requestRef.current) return
      setResults(response.results)
      setSearched(true)
    } catch (failure) {
      if (ticket !== requestRef.current) return
      setError(failure instanceof Error ? failure.message : 'A busca na Cifra Club falhou')
    } finally {
      if (ticket === requestRef.current) setSearching(false)
    }
  }, [query])

  const importChart = useCallback(
    async (result: CifraclubResult) => {
      setImporting(result.id)
      setError(null)
      const ticket = ++requestRef.current
      try {
        const fetched = await api.importWebChart(songId, result)
        if (ticket !== requestRef.current) return
        setChart(fetched)
        setChartMissing(false)
        setResults([])
        setQuery('')
        setComparison(null)
      } catch (failure) {
        if (ticket !== requestRef.current) return
        setError(failure instanceof Error ? failure.message : 'Falhou ao importar a cifra')
      } finally {
        if (ticket === requestRef.current) setImporting(null)
      }
    },
    [songId],
  )

  const compare = useCallback(async () => {
    if (!chart) return
    setComparing(true)
    setError(null)
    const ticket = ++requestRef.current
    try {
      const result = await api.compareWebChart(songId)
      if (ticket !== requestRef.current) return
      setComparison(result)
    } catch (failure) {
      if (ticket !== requestRef.current) return
      setError(failure instanceof Error ? failure.message : 'Falhou ao comparar com a análise')
    } finally {
      if (ticket === requestRef.current) setComparing(false)
    }
  }, [chart, songId])

  const remove = useCallback(async () => {
    if (!chart) return
    const ticket = ++requestRef.current
    try {
      await api.removeWebChart(songId)
      if (ticket !== requestRef.current) return
      setChart(null)
      setChartMissing(true)
      setComparison(null)
    } catch (failure) {
      if (ticket !== requestRef.current) return
      setError(failure instanceof Error ? failure.message : 'Falhou ao remover a cifra')
    }
  }, [chart, songId])

  return (
    <section className="rounded-xl border border-line bg-panel p-4 ">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Cifra da Cifra Club</h3>
        {chart && (
          <button
            type="button"
            onClick={() => void remove()}
            className="rounded-full border border-line px-3 py-1 text-[11px] font-medium text-ink-soft transition hover:border-rose-400 hover:text-rose-500 "
          >
            Remover
          </button>
        )}
      </div>

      {error && <p className="mb-3 text-xs text-rose-500">{error}</p>}

      {chartMissing && (
        <div>
          <p className="mb-2 text-xs text-ink-soft">
            Nenhuma cifra importada. Busque por esta música na Cifra Club:
          </p>
          <div className="flex gap-2">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => event.key === 'Enter' && void search()}
              placeholder="título e artista…"
              className="min-w-0 flex-1 rounded-lg border border-line bg-canvas px-3 py-2 text-sm placeholder:text-ink-faint focus:border-accent focus:outline-none "
            />
            <button
              type="button"
              onClick={() => void search()}
              disabled={searching || !query.trim()}
              className="shrink-0 rounded-lg border border-accent px-3 py-2 text-xs font-semibold text-accent transition hover:bg-accent-soft disabled:opacity-40 "
            >
              {searching ? '…' : 'Buscar'}
            </button>
          </div>

          {searched && !searching && results.length === 0 && (
            <p className="mt-3 text-xs text-ink-faint">
              A Cifra Club não encontrou nada com esse nome.
            </p>
          )}

          {results.length > 0 && (
            <ul className="mt-3 max-h-64 divide-y divide-[var(--color-line)] overflow-y-auto rounded-lg border border-line">
              {results.map((result) => (
                <li key={result.id} className="flex items-center gap-3 px-3 py-2">
                  {result.image && (
                    <img
                      src={result.image}
                      alt=""
                      className="h-9 w-9 shrink-0 rounded object-cover"
                      loading="lazy"
                    />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">{result.title}</p>
                    <p className="truncate text-xs text-ink-soft">
                      {result.artist || '—'}
                      {result.album ? ` · ${result.album}` : ''}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void importChart(result)}
                    disabled={importing === result.id}
                    className="shrink-0 rounded-full border border-accent px-3 py-1 text-xs font-medium text-accent transition hover:bg-accent-soft disabled:opacity-40 "
                  >
                    {importing === result.id ? '…' : 'Importar'}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {chart && (
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <span className="font-semibold text-ink">{chart.title}</span>
            {chart.artist && <span className="text-ink-soft">{chart.artist}</span>}
            {chart.key && (
              <span className="rounded-full bg-canvas px-2 py-0.5 text-[11px] text-ink-soft">
                tom {chart.key}
              </span>
            )}
            <span className="text-[11px] text-ink-faint">{chart.chords.length} acordes</span>
          </div>
          <a
            href={`https://www.cifraclub.com.br${chart.pageUrl}`}
            target="_blank"
            rel="noreferrer"
            className="text-[11px] text-indigo-500 hover:underline"
          >
            ver na Cifra Club →
          </a>

          {!comparison ? (
            <button
              type="button"
              onClick={() => void compare()}
              disabled={comparing}
              className="mt-3 w-full rounded-lg border border-accent px-3 py-2 text-xs font-semibold text-accent transition hover:bg-accent-soft disabled:opacity-40 "
            >
              {comparing ? 'Comparando com a análise…' : 'Comparar com a análise da música'}
            </button>
          ) : (
            <Comparison chart={chart} comparison={comparison} />
          )}
        </div>
      )}
    </section>
  )
}

/**
 * The comparison marks.
 *
 * The verdicts come back as spans with the chart's chord sequence aligned to
 * the detected ones, plus a per-bar view. The bars are what a reader points at
 * when the song moves, so that is the view drawn here — one cell per bar,
 * coloured by how the web chord and the heard chord agree.
 */
function Comparison({ chart, comparison }: { chart: WebChart; comparison: ChartComparison }) {
  const { stats, perBar } = comparison

  return (
    <div className="mt-3 space-y-3">
      <div className="flex flex-wrap gap-2 text-[11px]">
        <Stat value={stats.match} label="casa" dot="bg-emerald-500" />
        <Stat value={stats.partial} label="próximo" dot="bg-amber-500" />
        <Stat value={stats.diff} label="difere" dot="bg-rose-500" />
        <Stat value={stats.missing} label="não no cifra" dot="bg-sky-500" />
      </div>

      <div className="max-h-48 overflow-y-auto rounded-lg border border-line">
        <div className="grid grid-cols-[repeat(auto-fill,minmax(3.5rem,1fr))] gap-1 p-2">
          {perBar.map((bar) => (
            <div
              key={bar.bar}
              title={`Compasso ${bar.bar}: ${bar.detected ?? '—'} ${
                bar.web ? `→ cifra ${bar.web}` : ''
              }`}
              className={[
                'rounded border px-1 py-0.5 text-center',
                VERDICT_CLASS[bar.verdict] ?? 'bg-slate-500/15 border-slate-400/40 text-slate-600',
              ].join(' ')}
            >
              <span className="block text-[9px] font-semibold text-ink-faint">{bar.bar}</span>
              <span className="block truncate text-[11px] font-semibold">
                {bar.web ?? (bar.verdict === 'noChord' ? '·' : '—')}
              </span>
            </div>
          ))}
        </div>
      </div>

      <p className="text-[11px] text-ink-faint">
        {stats.detected} mudanças ouvidas comparadas com {chart.chords.length} escritas —{' '}
        {Math.round(((stats.match + stats.partial) / Math.max(1, stats.detected)) * 100)}% de
        concordância.
      </p>
    </div>
  )
}

function Stat({ value, label, dot }: { value: number; label: string; dot: string }) {
  return (
    <span className="flex items-center gap-1.5 rounded-full border border-line px-2 py-0.5 text-ink-soft">
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {value} {label}
    </span>
  )
}
