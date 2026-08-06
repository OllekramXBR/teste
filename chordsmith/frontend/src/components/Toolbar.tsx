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

function Control({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
        {label}
      </span>
      {children}
    </div>
  )
}

function Stepper({
  value,
  min,
  max,
  onChange,
  format,
}: {
  value: number
  min: number
  max: number
  onChange: (next: number) => void
  format: (value: number) => string
}) {
  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        aria-label="Decrease"
        disabled={value <= min}
        onClick={() => onChange(value - 1)}
        className="h-7 w-7 rounded bg-slate-200 text-sm font-bold text-slate-700 disabled:opacity-40 hover:bg-slate-300 "
      >
        −
      </button>
      <span className="w-14 text-center text-sm font-semibold tabular-nums">{format(value)}</span>
      <button
        type="button"
        aria-label="Increase"
        disabled={value >= max}
        onClick={() => onChange(value + 1)}
        className="h-7 w-7 rounded bg-slate-200 text-sm font-bold text-slate-700 disabled:opacity-40 hover:bg-slate-300 "
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
      className="h-1.5 w-24 cursor-pointer appearance-none rounded-full bg-slate-300 accent-indigo-600 dark:bg-slate-600"
    />
  )
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
    <div className="flex flex-wrap items-end gap-x-6 gap-y-4 rounded-xl border border-line bg-panel p-4">
      <Control label="Transpose">
        <Stepper
          value={settings.transpose}
          min={-11}
          max={11}
          onChange={(next) => onChange({ transpose: next })}
          format={(value) => (value > 0 ? `+${value}` : `${value}`)}
        />
        <span className="text-[10px] text-ink-faint">
          sounds in {soundingKey} {keyMode}
        </span>
      </Control>

      <Control label="Capo">
        <Stepper
          value={settings.capo}
          min={0}
          max={11}
          onChange={(next) => onChange({ capo: next })}
          format={(value) => (value === 0 ? 'off' : `fret ${value}`)}
        />
        <span className="text-[10px] text-ink-faint">shapes change, pitch does not</span>
      </Control>

      <Control label="Tempo">
        <select
          value={settings.rate}
          onChange={(event) => onChange({ rate: Number(event.target.value) })}
          className="h-7 rounded border border-line bg-panel px-2 text-sm "
        >
          {RATES.map((rate) => (
            <option key={rate} value={rate}>
              {Math.round(rate * 100)}%
            </option>
          ))}
        </select>
        <span className="text-[10px] text-ink-faint">pitch preserved</span>
      </Control>

      <Control label="Instrument">
        <select
          value={settings.instrument}
          onChange={(event) =>
            onChange({ instrument: event.target.value as ToolbarSettings['instrument'] })
          }
          className="h-7 rounded border border-line bg-panel px-2 text-sm "
        >
          <option value="guitar">Guitar</option>
          <option value="ukulele">Ukulele</option>
          <option value="piano">Piano</option>
        </select>
      </Control>

      <Control label="Song volume">
        <Slider
          value={settings.songVolume}
          label="Song volume"
          onChange={(next) => onChange({ songVolume: next })}
        />
      </Control>

      <Control label="Chord volume">
        <Slider
          value={settings.chordVolume}
          label="Chord volume"
          onChange={(next) => onChange({ chordVolume: next })}
        />
      </Control>

      <Control label="Metronome">
        <Slider
          value={settings.clickVolume}
          label="Metronome volume"
          onChange={(next) => onChange({ clickVolume: next })}
        />
      </Control>

      <Control label="Loop">
        {loopBars ? (
          <button
            type="button"
            onClick={onClearLoop}
            className="h-7 rounded bg-amber-400 px-3 text-xs font-semibold text-ink hover:bg-amber-300"
          >
            bars {loopBars.start}–{loopBars.end} · clear
          </button>
        ) : (
          <span className="text-[11px] text-ink-faint">click a bar number to start</span>
        )}
      </Control>

      <Control label="Auto-scroll">
        <button
          type="button"
          role="switch"
          aria-checked={settings.autoScroll}
          onClick={() => onChange({ autoScroll: !settings.autoScroll })}
          className={`h-7 w-14 rounded-full px-1 transition-colors ${
            settings.autoScroll ? 'bg-indigo-600' : 'bg-slate-300 dark:bg-slate-600'
          }`}
        >
          <span
            className={`block h-5 w-5 rounded-full bg-panel transition-transform ${
              settings.autoScroll ? 'translate-x-7' : ''
            }`}
          />
        </button>
      </Control>
    </div>
  )
}
