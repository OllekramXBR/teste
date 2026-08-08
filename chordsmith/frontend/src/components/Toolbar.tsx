import type { ReactNode } from 'react'
import type { Instrument } from '../lib/fretboard'
import { noteName } from '../lib/theory'

export interface ToolbarSettings {
  transpose: number
  capo: number
  rate: number
  songVolume: number
  chordVolume: number
  clickVolume: number
  instrument: Instrument['id'] | 'piano'
  autoScroll: boolean
  /** Collapse decoder extensions to the triad a hand actually makes. */
  simplify: boolean
  /** Bars of metronome before playback starts; 0 is off. */
  countIn: number
  /** Training wheels: pause just before each chord change until resumed. */
  pauseOnChange: boolean
}

interface ToolbarProps {
  settings: ToolbarSettings
  onChange: (patch: Partial<ToolbarSettings>) => void
  keyTonic: number
  keyMode: string
  useFlats: boolean
  loopBars: { start: number; end: number } | null
  onClearLoop: () => void
}

const RATES = [0.5, 0.65, 0.75, 0.9, 1, 1.15, 1.25]

/**
 * A group of controls that belong to one question — what key, how it plays,
 * how loud. Nine flat controls read as noise; three named groups read as a
 * mixing desk.
 */
function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="min-w-0">
      <legend className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-ink-faint">
        {title}
      </legend>
      <div className="flex flex-wrap items-start gap-x-5 gap-y-3">{children}</div>
    </fieldset>
  )
}

function Control({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className="text-[11px] font-medium text-ink-soft">{label}</span>
      {children}
    </label>
  )
}

function Stepper({
  value,
  min,
  max,
  onChange,
  format,
  decreaseLabel,
  increaseLabel,
}: {
  value: number
  min: number
  max: number
  onChange: (next: number) => void
  format: (value: number) => string
  decreaseLabel: string
  increaseLabel: string
}) {
  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        aria-label={decreaseLabel}
        disabled={value <= min}
        onClick={() => onChange(value - 1)}
        className="h-7 w-7 rounded bg-canvas text-sm font-bold text-ink transition-colors hover:bg-accent-soft disabled:opacity-40"
      >
        −
      </button>
      <span className="w-14 text-center text-sm font-semibold tabular-nums">{format(value)}</span>
      <button
        type="button"
        aria-label={increaseLabel}
        disabled={value >= max}
        onClick={() => onChange(value + 1)}
        className="h-7 w-7 rounded bg-canvas text-sm font-bold text-ink transition-colors hover:bg-accent-soft disabled:opacity-40"
      >
        +
      </button>
    </div>
  )
}

function Slider({
  value,
  onChange,
  label,
}: {
  value: number
  onChange: (next: number) => void
  label: string
}) {
  return (
    <input
      type="range"
      min={0}
      max={1}
      step={0.01}
      value={value}
      aria-label={label}
      onChange={(event) => onChange(Number(event.target.value))}
      className="h-7 w-24 text-accent"
    />
  )
}

function Switch({
  checked,
  onToggle,
  label,
}: {
  checked: boolean
  onToggle: () => void
  label: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={onToggle}
      className={`h-7 w-12 rounded-full px-1 transition-all ${
        checked
          ? 'bg-accent shadow-[0_0_10px_color-mix(in_oklab,var(--color-accent)_45%,transparent)]'
          : 'bg-line'
      }`}
    >
      <span
        className={`block h-5 w-5 rounded-full bg-panel shadow-sm transition-transform ${
          checked ? 'translate-x-5' : ''
        }`}
      />
    </button>
  )
}

/** A hairline between groups; hidden when the toolbar wraps into one column. */
function Divider() {
  return <div className="hidden w-px self-stretch bg-line/70 sm:block" aria-hidden="true" />
}

export function Toolbar({
  settings,
  onChange,
  keyTonic,
  keyMode,
  useFlats,
  loopBars,
  onClearLoop,
}: ToolbarProps) {
  const soundingKey = noteName(keyTonic + settings.transpose, useFlats)

  return (
    <div className="glass flex flex-wrap items-stretch gap-x-6 gap-y-5 rounded-xl p-4">
      <Group title="Tom">
        <Control label="Transpor">
          <Stepper
            value={settings.transpose}
            min={-11}
            max={11}
            onChange={(next) => onChange({ transpose: next })}
            format={(value) => (value > 0 ? `+${value}` : `${value}`)}
            decreaseLabel="Baixar meio tom"
            increaseLabel="Subir meio tom"
          />
          <span className="text-[10px] text-ink-faint">
            soa em {soundingKey} {keyMode === 'minor' ? 'menor' : 'maior'}
          </span>
        </Control>

        <Control label="Capotraste">
          <Stepper
            value={settings.capo}
            min={0}
            max={11}
            onChange={(next) => onChange({ capo: next })}
            format={(value) => (value === 0 ? 'sem' : `casa ${value}`)}
            decreaseLabel="Descer o capotraste"
            increaseLabel="Subir o capotraste"
          />
          <span className="text-[10px] text-ink-faint">muda o desenho, não o som</span>
        </Control>

        <Control label="Simplificar">
          <Switch
            checked={settings.simplify}
            onToggle={() => onChange({ simplify: !settings.simplify })}
            label="Simplificar os acordes"
          />
          <span className="text-[10px] text-ink-faint">só o acorde que a mão faz</span>
        </Control>
      </Group>

      <Divider />

      <Group title="Reprodução">
        <Control label="Andamento">
          <select
            value={settings.rate}
            onChange={(event) => onChange({ rate: Number(event.target.value) })}
            className="h-7 rounded border border-line bg-panel px-2 text-sm"
          >
            {RATES.map((rate) => (
              <option key={rate} value={rate}>
                {Math.round(rate * 100)}%
              </option>
            ))}
          </select>
          <span className="text-[10px] text-ink-faint">tom preservado</span>
        </Control>

        <Control label="Contagem">
          <select
            value={settings.countIn}
            onChange={(event) => onChange({ countIn: Number(event.target.value) })}
            className="h-7 rounded border border-line bg-panel px-2 text-sm"
          >
            <option value={0}>sem</option>
            <option value={1}>1 compasso</option>
            <option value={2}>2 compassos</option>
          </select>
          <span className="text-[10px] text-ink-faint">metrônomo antes de tocar</span>
        </Control>

        <Control label="Rolagem">
          <Switch
            checked={settings.autoScroll}
            onToggle={() => onChange({ autoScroll: !settings.autoScroll })}
            label="Rolagem automática"
          />
          <span className="text-[10px] text-ink-faint">a grade segue a música</span>
        </Control>

        <Control label="Treino">
          <Switch
            checked={settings.pauseOnChange}
            onToggle={() => onChange({ pauseOnChange: !settings.pauseOnChange })}
            label="Pausar nas trocas de acorde"
          />
          <span className="text-[10px] text-ink-faint">pausa antes de cada troca</span>
        </Control>
      </Group>

      <Divider />

      <Group title="Mixagem">
        <Control label="Música">
          <Slider
            value={settings.songVolume}
            label="Volume da música"
            onChange={(next) => onChange({ songVolume: next })}
          />
        </Control>

        <Control label="Acordes">
          <Slider
            value={settings.chordVolume}
            label="Volume dos acordes"
            onChange={(next) => onChange({ chordVolume: next })}
          />
        </Control>

        <Control label="Metrônomo">
          <Slider
            value={settings.clickVolume}
            label="Volume do metrônomo"
            onChange={(next) => onChange({ clickVolume: next })}
          />
        </Control>
      </Group>

      <Divider />

      <Group title="Exibição">
        <Control label="Instrumento">
          <select
            value={settings.instrument}
            onChange={(event) =>
              onChange({ instrument: event.target.value as ToolbarSettings['instrument'] })
            }
            className="h-7 rounded border border-line bg-panel px-2 text-sm"
          >
            <option value="guitar">Violão</option>
            <option value="ukulele">Ukulele</option>
            <option value="piano">Teclado</option>
          </select>
        </Control>

        <Control label="Loop">
          {loopBars ? (
            <button
              type="button"
              onClick={onClearLoop}
              className="h-7 rounded bg-amber-400 px-3 text-xs font-semibold text-slate-900 transition-colors hover:bg-amber-300"
            >
              compassos {loopBars.start}–{loopBars.end} · limpar
            </button>
          ) : (
            <span className="max-w-36 text-[11px] leading-tight text-ink-faint">
              clique no número de um compasso na grade
            </span>
          )}
        </Control>
      </Group>
    </div>
  )
}
