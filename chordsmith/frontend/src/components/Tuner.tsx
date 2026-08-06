import { useCallback, useEffect, useRef, useState } from 'react'
import { noteName } from '../lib/theory'

interface Reading {
  frequency: number
  midi: number
  cents: number
  clarity: number
}

const SAMPLE_SIZE = 2048
const MIN_CLARITY = 0.55

/**
 * Pitch detection by normalised autocorrelation.
 *
 * The plain autocorrelation peak is biased toward long lags, so each lag is
 * normalised by the energy in its window; the returned clarity is that
 * normalised peak, which doubles as a "is this actually a pitch" test.
 */
function detectPitch(buffer: Float32Array, sampleRate: number): Reading | null {
  let rms = 0
  for (const sample of buffer) rms += sample * sample
  rms = Math.sqrt(rms / buffer.length)
  if (rms < 0.008) return null // effectively silence

  const minLag = Math.floor(sampleRate / 1200) // ~1200 Hz ceiling
  const maxLag = Math.floor(sampleRate / 60) // ~60 Hz floor
  let bestLag = -1
  let bestScore = 0

  for (let lag = minLag; lag <= maxLag && lag < buffer.length; lag += 1) {
    let correlation = 0
    let energy = 0
    for (let index = 0; index + lag < buffer.length; index += 1) {
      correlation += buffer[index] * buffer[index + lag]
      energy += buffer[index + lag] * buffer[index + lag]
    }
    const score = energy > 0 ? correlation / Math.sqrt(energy) : 0
    if (score > bestScore) {
      bestScore = score
      bestLag = lag
    }
  }
  if (bestLag < 0) return null

  const clarity = bestScore / Math.sqrt(buffer.length)
  if (clarity < MIN_CLARITY) return null

  const frequency = sampleRate / bestLag
  const midi = 69 + 12 * Math.log2(frequency / 440)
  const nearest = Math.round(midi)
  return {
    frequency,
    midi: nearest,
    cents: Math.round((midi - nearest) * 100),
    clarity: Math.min(clarity, 1),
  }
}

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
        setReading(detectPitch(buffer, context.sampleRate))
        frameRef.current = requestAnimationFrame(loop)
      }
      setActive(true)
      loop()
    } catch {
      setError('Microphone access was denied. Allow it in your browser to use the tuner.')
    }
  }, [])

  const cents = reading?.cents ?? 0
  const inTune = reading !== null && Math.abs(cents) <= 5

  return (
    <div className="rounded-xl border border-line bg-panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold">Chromatic tuner</h3>
        <button
          type="button"
          onClick={() => (active ? stop() : void start())}
          className={`rounded px-3 py-1 text-xs font-semibold ${
            active
              ? 'bg-rose-500 text-white hover:bg-rose-400'
              : 'bg-indigo-600 text-white hover:bg-indigo-500'
          }`}
        >
          {active ? 'Stop' : 'Start'}
        </button>
      </div>

      {error && <p className="text-xs text-rose-500">{error}</p>}

      {!active && !error && (
        <p className="text-xs text-ink-soft">
          Uses your microphone to show the nearest note and how many cents off you are.
        </p>
      )}

      {active && (
        <div className="space-y-3">
          <div className="text-center">
            <div
              className={`text-4xl font-bold tabular-nums ${
                inTune ? 'text-emerald-500' : 'text-slate-700'
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
              {reading ? `${reading.frequency.toFixed(1)} Hz · ${cents > 0 ? '+' : ''}${cents} cents` : 'play a note'}
            </div>
          </div>

          <div className="relative h-3 rounded-full bg-slate-200 ">
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
