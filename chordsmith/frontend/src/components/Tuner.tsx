import { useCallback, useEffect, useRef, useState } from 'react'
import { detectPitch, type PitchReading } from '../lib/pitch'
import { noteName } from '../lib/theory'

type Reading = PitchReading

const SAMPLE_SIZE = 2048
const MIN_CLARITY = 0.55

/** Chromatic tuner driven by the microphone. */
export function Tuner() {
  const [active, setActive] = useState(false)
  const [reading, setReading] = useState<Reading | null>(null)
  const [error, setError] = useState<string | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const frameRef = useRef<number | null>(null)

  const stop = useCallback(() => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    frameRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    void contextRef.current?.close()
    contextRef.current = null
    setActive(false)
    setReading(null)
  }, [])

  useEffect(() => stop, [stop])

  const start = useCallback(async () => {
    setError(null)
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
        const detected = detectPitch(buffer, context.sampleRate)
        setReading(detected && detected.clarity >= MIN_CLARITY ? detected : null)
        frameRef.current = requestAnimationFrame(loop)
      }
      setActive(true)
      loop()
    } catch {
      setError('O acesso ao microfone foi negado. Libere no navegador para usar o afinador.')
    }
  }, [])

  const cents = reading?.cents ?? 0
  const inTune = reading !== null && Math.abs(cents) <= 5

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
          Afinador cromático
        </h3>
        <button
          type="button"
          onClick={() => (active ? stop() : void start())}
          className={`rounded px-3 py-1 text-xs font-semibold transition-colors ${
            active
              ? 'bg-rose-500 text-white hover:bg-rose-400'
              : 'bg-accent text-canvas hover:brightness-110'
          }`}
        >
          {active ? 'Parar' : 'Ligar'}
        </button>
      </div>

      {error && <p className="text-xs text-rose-500">{error}</p>}

      {!active && !error && (
        <p className="text-xs text-ink-soft">
          Usa o microfone para mostrar a nota mais próxima e quantos cents faltam para afinar.
        </p>
      )}

      {active && (
        <div className="space-y-3">
          <div className="text-center">
            <div
              className={`text-4xl font-bold tabular-nums ${
                inTune ? 'text-emerald-500' : 'text-ink'
              }`}
            >
              {reading ? noteName(reading.midi % 12) : '—'}
              {reading && (
                <span className="ml-1 align-super text-sm text-ink-faint">
                  {Math.floor(reading.midi / 12) - 1}
                </span>
              )}
            </div>
            <div className="text-xs text-ink-faint tabular-nums">
              {reading ? `${reading.frequency.toFixed(1)} Hz · ${cents > 0 ? '+' : ''}${cents} cents` : 'toque uma nota'}
            </div>
          </div>

          <div className="relative h-3 rounded-full bg-canvas">
            <div className="absolute left-1/2 top-0 h-3 w-0.5 -translate-x-1/2 bg-slate-400" />
            {reading && (
              <div
                className={`absolute top-0 h-3 w-2 -translate-x-1/2 rounded-full transition-all ${
                  inTune ? 'bg-emerald-500' : 'bg-amber-500'
                }`}
                style={{ left: `${50 + Math.max(-50, Math.min(50, cents))}%` }}
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}
