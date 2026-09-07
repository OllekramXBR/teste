import { useCallback, useEffect, useRef, useState } from 'react'

import { QUALITIES } from '../lib/theory'

export interface Heard {
  /** Best chord as `root` (0–11) and quality key, or null when nothing is playing. */
  root: number | null
  quality: string
  /** 0–1. How much better this chord fit than the runner-up. */
  confidence: number
  /** Normalised energy per pitch class, for drawing what the microphone hears. */
  chroma: number[]
  /** Overall input level, so the interface can say "play something". */
  level: number
}

const SILENT: Heard = { root: null, quality: '', confidence: 0, chroma: new Array(12).fill(0), level: 0 }

// Guitars and voices live here. Below this is room noise and mains hum; above
// it, harmonics that mostly repeat what the lower ones already said.
const LOW_HZ = 70
const HIGH_HZ = 2200

// A chord has to hold this long before it is announced. Without it the readout
// flickers through every passing shape of a strum, which is unreadable and
// makes the detector look worse than it is.
const HISTORY = 6
const LEVEL_FLOOR = 0.012

/**
 * Weights matching the analysis engine's: root and fifth carry the identity of
 * a chord, extensions are weak in a chroma vector and over-trigger if trusted.
 */
const INTERVAL_WEIGHT: Record<number, number> = {
  0: 1.35,
  7: 1.0,
  3: 1.0,
  4: 1.0,
  6: 0.9,
  8: 0.9,
  5: 1.0,
  2: 0.9,
  9: 0.65,
  10: 0.7,
  11: 0.7,
}

const TEMPLATES = buildTemplates()

/**
 * What chord is being played into the microphone, right now.
 *
 * The same idea as the offline decoder — fold the spectrum into twelve pitch
 * classes and compare against weighted chord templates — but with none of its
 * advantages: no beat grid, no key estimate, no Viterbi pass over the whole
 * song. A live detector only ever sees the present, so it makes up for that by
 * refusing to speak until a chord has held for several frames.
 *
 * The stream is stopped on unmount. A page that quietly keeps a microphone open
 * is a page nobody should trust.
 */
export function useChordListener() {
  const [listening, setListening] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [heard, setHeard] = useState<Heard>(SILENT)

  const contextRef = useRef<AudioContext | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const frameRef = useRef<number | null>(null)
  const historyRef = useRef<string[]>([])

  const stop = useCallback(() => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    frameRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    void contextRef.current?.close()
    contextRef.current = null
    analyserRef.current = null
    historyRef.current = []
    setListening(false)
    setHeard(SILENT)
  }, [])

  const start = useCallback(async () => {
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          // All three would fight the thing being measured: gain control moves
          // the level, noise suppression eats sustained tones, and echo
          // cancellation is built to remove exactly what a speaker is playing.
          autoGainControl: false,
          noiseSuppression: false,
          echoCancellation: false,
        },
      })
      const context = new AudioContext()
      const analyser = context.createAnalyser()
      analyser.fftSize = 8192
      analyser.smoothingTimeConstant = 0.6
      context.createMediaStreamSource(stream).connect(analyser)

      streamRef.current = stream
      contextRef.current = context
      analyserRef.current = analyser
      setListening(true)
    } catch (failure) {
      setError(
        failure instanceof Error && failure.name === 'NotAllowedError'
          ? 'Preciso da permissão do microfone para ouvir.'
          : 'Não consegui abrir o microfone.',
      )
    }
  }, [])

  useEffect(() => {
    if (!listening) return
    const analyser = analyserRef.current
    const context = contextRef.current
    if (!analyser || !context) return

    const spectrum = new Float32Array(analyser.frequencyBinCount)
    const binHz = context.sampleRate / analyser.fftSize

    const step = () => {
      analyser.getFloatFrequencyData(spectrum)

      const chroma = new Array(12).fill(0)
      let total = 0
      for (let bin = 1; bin < spectrum.length; bin += 1) {
        const frequency = bin * binHz
        if (frequency < LOW_HZ || frequency > HIGH_HZ) continue
        // getFloatFrequencyData is in decibels; back to a linear magnitude so
        // that adding two bins means adding two amounts of energy.
        const magnitude = Math.pow(10, spectrum[bin] / 20)
        const pitch = Math.round(12 * Math.log2(frequency / 440) + 69)
        chroma[((pitch % 12) + 12) % 12] += magnitude
        total += magnitude
      }

      const level = total
      const peak = Math.max(...chroma)
      const normalised = peak > 0 ? chroma.map((value) => value / peak) : chroma

      let best = SILENT.quality
      let bestRoot: number | null = null
      let bestScore = 0
      let runnerUp = 0

      if (level > LEVEL_FLOOR) {
        for (const template of TEMPLATES) {
          const score = cosine(normalised, template.vector)
          if (score > bestScore) {
            runnerUp = bestScore
            bestScore = score
            bestRoot = template.root
            best = template.quality
          } else if (score > runnerUp) {
            runnerUp = score
          }
        }
      }

      const key = bestRoot === null ? '' : `${bestRoot}:${best}`
      const history = historyRef.current
      history.push(key)
      if (history.length > HISTORY) history.shift()

      // Only announce a chord that has been the answer for most of the window.
      const counts = new Map<string, number>()
      for (const entry of history) counts.set(entry, (counts.get(entry) ?? 0) + 1)
      const [settled, votes] = [...counts.entries()].reduce((a, b) => (b[1] > a[1] ? b : a), ['', 0])

      const agreed = votes >= Math.ceil(HISTORY * 0.6) && settled !== ''
      setHeard({
        root: agreed ? Number(settled.split(':')[0]) : null,
        quality: agreed ? settled.split(':')[1] : '',
        confidence: bestScore > 0 ? Math.max(0, bestScore - runnerUp) / bestScore : 0,
        chroma: normalised,
        level,
      })

      frameRef.current = requestAnimationFrame(step)
    }

    frameRef.current = requestAnimationFrame(step)
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    }
  }, [listening])

  useEffect(() => stop, [stop])

  return { listening, error, heard, start, stop }
}

function buildTemplates() {
  const templates: { root: number; quality: string; vector: number[] }[] = []
  for (const [quality, intervals] of Object.entries(QUALITIES)) {
    for (let root = 0; root < 12; root += 1) {
      const vector = new Array(12).fill(0)
      for (const interval of intervals) {
        vector[(root + interval) % 12] = INTERVAL_WEIGHT[interval] ?? 0.8
      }
      templates.push({ root, quality, vector })
    }
  }
  return templates
}

function cosine(a: number[], b: number[]): number {
  let dot = 0
  let normA = 0
  let normB = 0
  for (let index = 0; index < 12; index += 1) {
    dot += a[index] * b[index]
    normA += a[index] * a[index]
    normB += b[index] * b[index]
  }
  return normA > 0 && normB > 0 ? dot / Math.sqrt(normA * normB) : 0
}
