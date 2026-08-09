/** Pitch detection by normalised autocorrelation, shared by the tuner and
 * the vocal-range meter.
 *
 * The plain autocorrelation peak is biased toward long lags, so each lag is
 * normalised by the energy in its window; the returned clarity is that
 * normalised peak, which doubles as an "is this actually a pitch" test.
 */

export interface PitchReading {
  frequency: number
  midi: number
  cents: number
  clarity: number
}

export function detectPitch(buffer: Float32Array, sampleRate: number): PitchReading | null {
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
