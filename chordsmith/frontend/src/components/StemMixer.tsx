import type { Stem, StemName } from '../lib/api'
import type { StemMix } from '../hooks/useStemPlayer'

interface Props {
  stems: Stem[]
  mix: Record<string, StemMix>
  solo: StemName | null
  onVolume: (name: StemName, volume: number) => void
  onMute: (name: StemName) => void
  onSolo: (name: StemName) => void
}

/** One-click presets for what people actually do with a set of stems. */
const PRESETS: { id: string; label: string; hint: string; mute: StemName[] }[] = [
  { id: 'full', label: 'Completo', hint: 'Tudo tocando', mute: [] },
  {
    id: 'sing',
    label: 'Eu canto',
    hint: 'Tira a voz principal, mantém os backing vocals',
    mute: ['lead'],
  },
  {
    id: 'instrumental',
    label: 'Instrumental',
    hint: 'Sem voz nenhuma',
    mute: ['lead', 'backing'],
  },
  { id: 'play', label: 'Eu toco', hint: 'Tira a harmonia, mantém voz e base', mute: ['other'] },
]

/**
 * Per-stem level, mute and solo.
 *
 * The presets exist because the useful combinations are few and the fiddly part
 * is remembering which stem holds what. "Eu canto" is the one this whole
 * feature was built for: the lead vocal goes, the backing vocals stay, and the
 * singer is the only lead voice in the room.
 */
export function StemMixer({ stems, mix, solo, onVolume, onMute, onSolo }: Props) {
  const applyPreset = (mute: StemName[]) => {
    for (const stem of stems) {
      const shouldMute = mute.includes(stem.name)
      const isMuted = mix[stem.name]?.muted ?? false
      if (shouldMute !== isMuted) onMute(stem.name)
    }
    if (solo) onSolo(solo)
  }

  return (
    <section className="rounded-lg border border-line bg-panel p-4 ">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold tracking-tight">Mixer</h2>
        <div className="flex flex-wrap gap-1">
          {PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              title={preset.hint}
              onClick={() => applyPreset(preset.mute)}
              className="rounded-full border border-line px-3 py-1 text-xs font-medium transition hover:border-accent hover:text-accent"
            >
              {preset.label}
            </button>
          ))}
        </div>
      </div>

      <ul className="space-y-2">
        {stems.map((stem) => {
          const settings = mix[stem.name] ?? { volume: 1, muted: false }
          const silenced = solo ? solo !== stem.name : settings.muted
          return (
            <li key={stem.name} className="flex items-center gap-3">
              <div className="flex gap-1">
                <button
                  type="button"
                  aria-pressed={settings.muted}
                  onClick={() => onMute(stem.name)}
                  className={toggleClass(settings.muted, 'rose')}
                  title="Silenciar"
                >
                  M
                </button>
                <button
                  type="button"
                  aria-pressed={solo === stem.name}
                  onClick={() => onSolo(stem.name)}
                  className={toggleClass(solo === stem.name, 'amber')}
                  title="Ouvir só este"
                >
                  S
                </button>
              </div>
              <span
                className={[
                  'w-24 shrink-0 text-sm transition-opacity',
                  silenced ? 'opacity-40' : '',
                ].join(' ')}
              >
                {stem.label}
              </span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={settings.volume}
                onChange={(event) => onVolume(stem.name, Number(event.target.value))}
                className="h-1 w-full accent-accent"
                aria-label={`Volume de ${stem.label}`}
              />
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function toggleClass(active: boolean, tone: 'rose' | 'amber'): string {
  const base =
    'h-7 w-7 rounded text-xs font-bold transition border focus-visible:outline-2 focus-visible:outline-accent'
  if (!active) {
    return `${base} border-line text-ink-soft hover:border-slate-400  `
  }
  return tone === 'rose'
    ? `${base} border-rose-500 bg-rose-500 text-white`
    : `${base} border-amber-500 bg-amber-500 text-white`
}
