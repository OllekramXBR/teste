import { useMemo, useState } from 'react'

import { ChordPopover } from '../components/ChordPopover'
import { br } from '../lib/brazilian'
import { ALL_KEYS, formatChord, noteName, QUALITIES, QUALITY_LABELS } from '../lib/theory'
import { Page, PageHeader } from '../components/Page'

/**
 * Every chord the app knows, on any instrument it can finger.
 *
 * A grid rather than a search box: someone looking up a chord usually knows the
 * root and is choosing among qualities, or knows the quality and is
 * transposing. Both of those are reading tasks, and a table answers them
 * without anybody typing.
 */
export function DictionaryPage() {
  const [useFlats, setUseFlats] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [quality, setQuality] = useState<string | null>(null)

  const qualities = useMemo(() => Object.keys(QUALITIES), [])
  const shown = quality ? [quality] : qualities

  return (
    <Page>
      <PageHeader
        title="Dicionário de acordes"
        description="Toque em qualquer acorde para ver a digitação no seu instrumento. Notação brasileira: 7M para a sétima maior, ° para diminuto, + para aumentado."
      />

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setUseFlats((previous) => !previous)}
          className="rounded-full border border-line px-3 py-1 text-xs font-medium "
        >
          {useFlats ? 'bemóis (Bb)' : 'sustenidos (A#)'}
        </button>
        <select
          value={quality ?? ''}
          onChange={(event) => setQuality(event.target.value || null)}
          className="rounded-full border border-line bg-panel px-3 py-1 text-xs "
        >
          <option value="">todas as qualidades</option>
          {qualities.map((option) => (
            <option key={option} value={option}>
              {QUALITY_LABELS[option] ?? (option || "maior")}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-5">
        {shown.map((option) => (
          <section key={option}>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">
              {QUALITY_LABELS[option] ?? (option || "maior")}
            </h2>
            <div className="flex flex-wrap gap-1.5">
              {ALL_KEYS.map((root) => {
                const label = formatChord(root, option, useFlats)
                return (
                  <button
                    key={`${root}-${option}`}
                    type="button"
                    onClick={() => setSelected(br(label))}
                    className="rounded-lg border border-line bg-panel px-3 py-2 text-sm font-semibold transition hover:border-accent hover:text-accent "
                  >
                    {br(label)}
                  </button>
                )
              })}
            </div>
          </section>
        ))}
      </div>

      <p className="text-[11px] text-ink-faint">
        As formas são procuradas no braço de cada instrumento, não tiradas de uma tabela — por isso
        cavaquinho e viola caipira funcionam igual ao violão. {ALL_KEYS.length * qualities.length}{' '}
        acordes ao todo, sem contar as posições alternativas de cada um.
      </p>

      {selected && (
        <ChordPopover label={selected} useFlats={useFlats} onClose={() => setSelected(null)} />
      )}
    </Page>
  )
}

/** Roots as note names, for anything that wants to label an axis. */
export const ROOT_NAMES = (useFlats: boolean) => ALL_KEYS.map((root) => noteName(root, useFlats))
