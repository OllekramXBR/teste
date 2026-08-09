import { useCallback, useEffect, useRef, useState } from 'react'

import { detectPitch } from '../lib/pitch'
import { mod12, noteName } from '../lib/theory'

export interface VocalRangeValue {
  /** MIDI numbers of the lowest and highest comfortable sung notes. */
  low: number
  high: number
}

const STORAGE_KEY = 'metatron.vocalRange.v1'
const SAMPLE_SIZE = 2048
// Stricter than the tuner: a range built from one squeaky frame is a lie.
const MIN_CLARITY = 0.75
const STABLE_FRAMES = 4
// Human singing lives here; anything outside is the guitar or a harmonic.
const MIDI_FLOOR = 36 // C2
const MIDI_CEIL = 84 // C6

export function loadVocalRange(): VocalRangeValue | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as VocalRangeValue
    if (Number.isInteger(parsed.low) && Number.isInteger(parsed.high) && parsed.low < parsed.high) {
      return parsed
    }
    return null
  } catch {
    return null
  }
}

export function midiLabel(midi: number, useFlats = false): string {
  return `${noteName(mod12(midi), useFlats)}${Math.floor(midi / 12) - 1}`
}

interface Props {
  value: VocalRangeValue | null
  onChange: (value: VocalRangeValue | null) => void
}

/**
 * Measure the singer, once.
 *
 * Slide from your lowest comfortable note to your highest while this
 * listens; a note only counts after a few stable frames, so a cough or the
 * guitar's sympathetic string does not become your new record. The range is
 * saved on this device and every key suggestion in the app reads it.
 */
export function VocalRange({ value, onChange }: Props) {
  const [active, setActive] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [live, setLive] = useState<{ midi: number; low: number | null; high: number | null }>({
    midi: -1,
    low: null,
    high: null,
  })

  const streamRef = useRef<MediaStream | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const frameRef = useRef<number | null>(null)
  const stableRef = useRef<{ midi: number; frames: number }>({ midi: -1, frames: 0 })
  const boundsRef = useRef<{ low: number | null; high: number | null }>({ low: null, high: null })

  const stop = useCallback(() => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    frameRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    void contextRef.current?.close()
    contextRef.current = null
    setActive(false)
  }, [])

  useEffect(() => stop, [stop])

  const start = useCallback(async () => {
    setError(null)
    boundsRef.current = { low: null, high: null }
    stableRef.current = { midi: -1, frames: 0 }
    setLive({ midi: -1, low: null, high: null })
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      })
      streamRef.current = stream
      const context = new AudioContext()
      contextRef.current = context
      const source = context.createMediaStreamSource(stream)
      const analyser = context.createAnalyser()
      analyser.fftSize = SAMPLE_SIZE * 2
      source.connect(analyser)

      const buffer = new Float32Array(SAMPLE_SIZE)
      const loop = () => {
        analyser.getFloatTimeDomainData(buffer)
        const reading = detectPitch(buffer, context.sampleRate)
        if (
          reading &&
          reading.clarity >= MIN_CLARITY &&
          reading.midi >= MIDI_FLOOR &&
          reading.midi <= MIDI_CEIL
        ) {
          const stable = stableRef.current
          stableRef.current =
            stable.midi === reading.midi
              ? { midi: reading.midi, frames: stable.frames + 1 }
              : { midi: reading.midi, frames: 1 }
          if (stableRef.current.frames >= STABLE_FRAMES) {
            const bounds = boundsRef.current
            if (bounds.low === null || reading.midi < bounds.low) bounds.low = reading.midi
            if (bounds.high === null || reading.midi > bounds.high) bounds.high = reading.midi
          }
          setLive({ midi: reading.midi, ...boundsRef.current })
        } else {
          setLive((previous) => ({ ...previous, midi: -1 }))
        }
        frameRef.current = requestAnimationFrame(loop)
      }
      setActive(true)
      loop()
    } catch {
      setError('O acesso ao microfone foi negado. Libere no navegador para medir a voz.')
    }
  }, [])

  const save = useCallback(() => {
    const bounds = boundsRef.current
    if (bounds.low === null || bounds.high === null || bounds.high - bounds.low < 5) {
      setError('Cante do seu grave ao seu agudo antes de salvar — pegue pelo menos meia oitava.')
      return
    }
    const next = { low: bounds.low, high: bounds.high }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    onChange(next)
    stop()
  }, [onChange, stop])

  const clear = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    onChange(null)
  }, [onChange])

  if (!active) {
    return (
      <div className="rounded-lg border border-dashed border-line/70 px-3 py-2.5 text-xs">
        {value ? (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-ink-soft">
              Sua voz:{' '}
              <strong className="text-flame">
                {midiLabel(value.low)}–{midiLabel(value.high)}
              </strong>
            </span>
            <span className="flex gap-2">
              <button
                type="button"
                onClick={() => void start()}
                className="font-medium text-accent hover:brightness-125"
              >
                medir de novo
              </button>
              <button
                type="button"
                onClick={clear}
                className="text-ink-faint hover:text-rose-500"
              >
                esquecer
              </button>
            </span>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-ink-soft">
              Meça sua voz uma vez e os tons ganham um aviso de “cabe na sua voz”.
            </span>
            <button
              type="button"
              onClick={() => void start()}
              className="shrink-0 rounded-full bg-accent px-3 py-1 font-semibold text-canvas transition hover:brightness-110"
            >
              Medir minha voz
            </button>
          </div>
        )}
        {error && <p className="mt-1.5 text-rose-500">{error}</p>}
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-flame/40 bg-flame-soft/60 px-3 py-2.5 text-xs">
      <p className="text-ink-soft">
        Deslize a voz do seu <strong>grave confortável</strong> até o seu{' '}
        <strong>agudo confortável</strong> (um “aaah” contínuo serve).
      </p>
      <div className="mt-2 flex items-center justify-between gap-3 tabular-nums">
        <span className="text-2xl font-extrabold text-ink">
          {live.midi > 0 ? midiLabel(live.midi) : '—'}
        </span>
        <span className="text-ink-soft">
          grave <strong>{live.low !== null ? midiLabel(live.low) : '—'}</strong> · agudo{' '}
          <strong>{live.high !== null ? midiLabel(live.high) : '—'}</strong>
        </span>
        <span className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={save}
            className="rounded-full bg-accent px-3 py-1 font-semibold text-canvas transition hover:brightness-110"
          >
            Salvar
          </button>
          <button
            type="button"
            onClick={stop}
            className="rounded-full border border-line px-3 py-1 font-medium text-ink-soft"
          >
            Cancelar
          </button>
        </span>
      </div>
      {error && <p className="mt-1.5 text-rose-500">{error}</p>}
    </div>
  )
}
