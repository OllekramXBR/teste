import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import type { Stem, StemName } from '../lib/api'

export interface StemMix {
  /** 0..1. Independent of muting, so unmuting restores the level you set. */
  volume: number
  muted: boolean
}

export interface StemPlayerState {
  ready: boolean
  loading: boolean
  playing: boolean
  currentTime: number
  duration: number
  /** 0..1 across all stems, for a progress bar while they decode. */
  loaded: number
  error: string | null
}

const SILENT = 0.0001

/**
 * Synchronised playback of several stems at once.
 *
 * This deliberately does not use one `<audio>` element per stem. Several media
 * elements started together drift — each has its own clock and its own buffering
 * decisions, and a few tens of milliseconds of drift between a voice and a drum
 * kit is audible as flam. Every stem here is decoded into memory and played from
 * one `AudioContext`, scheduled against a single clock, so they cannot separate.
 *
 * Holding the whole song in RAM is the point rather than the cost: on stage
 * there is no network left in the path, nothing to re-buffer, and no request
 * that can fail halfway through the second chorus.
 */
export function useStemPlayer(stems: Stem[]) {
  const contextRef = useRef<AudioContext | null>(null)
  const buffersRef = useRef<Map<StemName, AudioBuffer>>(new Map())
  const sourcesRef = useRef<Map<StemName, AudioBufferSourceNode>>(new Map())
  const gainsRef = useRef<Map<StemName, GainNode>>(new Map())
  const masterRef = useRef<GainNode | null>(null)
  // Where playback started, in both clocks, so position is derived rather than
  // polled from anything that could disagree with what you hear.
  const startedAtRef = useRef(0)
  const offsetRef = useRef(0)
  const frameRef = useRef<number | null>(null)
  const rateRef = useRef(1)

  const [state, setState] = useState<StemPlayerState>({
    ready: false,
    loading: false,
    playing: false,
    currentTime: 0,
    duration: 0,
    loaded: 0,
    error: null,
  })

  const [mix, setMix] = useState<Record<string, StemMix>>({})
  const [solo, setSolo] = useState<StemName | null>(null)

  const names = useMemo(() => stems.map((stem) => stem.name), [stems])
  const key = useMemo(() => stems.map((stem) => stem.url).join('|'), [stems])

  useEffect(() => {
    setMix((previous) => {
      const next: Record<string, StemMix> = {}
      for (const name of names) next[name] = previous[name] ?? { volume: 1, muted: false }
      return next
    })
  }, [names])

  // Decode every stem up front. Partial readiness is not offered on purpose:
  // playing three of four stems would sound like a mistake in the recording.
  useEffect(() => {
    if (!stems.length) {
      setState((previous) => ({ ...previous, ready: false, duration: 0 }))
      return
    }

    let cancelled = false
    const context = contextRef.current ?? new AudioContext()
    contextRef.current = context
    if (!masterRef.current) {
      masterRef.current = context.createGain()
      masterRef.current.connect(context.destination)
    }

    setState((previous) => ({ ...previous, loading: true, ready: false, loaded: 0, error: null }))

    let done = 0
    const load = async (stem: Stem) => {
      const response = await fetch(stem.url)
      if (!response.ok) throw new Error(`${stem.label}: HTTP ${response.status}`)
      const buffer = await context.decodeAudioData(await response.arrayBuffer())
      if (cancelled) return
      buffersRef.current.set(stem.name, buffer)
      done += 1
      setState((previous) => ({ ...previous, loaded: done / stems.length }))
    }

    Promise.all(stems.map(load))
      .then(() => {
        if (cancelled) return
        const duration = Math.max(
          ...Array.from(buffersRef.current.values(), (buffer) => buffer.duration),
          0,
        )
        setState((previous) => ({ ...previous, ready: true, loading: false, duration }))
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setState((previous) => ({
          ...previous,
          loading: false,
          ready: false,
          error: error instanceof Error ? error.message : 'The stems could not be loaded',
        }))
      })

    return () => {
      cancelled = true
    }
  }, [key, stems])

  const applyGains = useCallback(() => {
    const context = contextRef.current
    if (!context) return
    for (const [name, gain] of gainsRef.current) {
      const settings = mix[name] ?? { volume: 1, muted: false }
      const audible = solo ? solo === name : !settings.muted
      // A short ramp rather than a step: an instant gain change on a running
      // buffer clicks, and a click through a PA at volume is unpleasant.
      gain.gain.setTargetAtTime(audible ? settings.volume : SILENT, context.currentTime, 0.015)
    }
  }, [mix, solo])

  useEffect(() => {
    applyGains()
  }, [applyGains])

  const stopSources = useCallback(() => {
    for (const source of sourcesRef.current.values()) {
      try {
        source.stop()
      } catch {
        // Already stopped; nothing to undo.
      }
      source.disconnect()
    }
    sourcesRef.current.clear()
  }, [])

  const startAt = useCallback(
    (offset: number) => {
      const context = contextRef.current
      const master = masterRef.current
      if (!context || !master) return

      stopSources()
      const when = context.currentTime + 0.06 // a beat of headroom to schedule all of them
      for (const [name, buffer] of buffersRef.current) {
        const source = context.createBufferSource()
        source.buffer = buffer
        source.playbackRate.value = rateRef.current

        let gain = gainsRef.current.get(name)
        if (!gain) {
          gain = context.createGain()
          gain.connect(master)
          gainsRef.current.set(name, gain)
        }
        source.connect(gain)
        source.start(when, Math.max(0, Math.min(offset, buffer.duration)))
        sourcesRef.current.set(name, source)
      }

      startedAtRef.current = when
      offsetRef.current = offset
      applyGains()
    },
    [applyGains, stopSources],
  )

  const play = useCallback(async () => {
    const context = contextRef.current
    if (!context || !state.ready) return
    if (context.state === 'suspended') await context.resume()
    startAt(offsetRef.current)
    setState((previous) => ({ ...previous, playing: true }))
  }, [startAt, state.ready])

  const pause = useCallback(() => {
    const context = contextRef.current
    if (!context) return
    offsetRef.current = position(context, startedAtRef.current, offsetRef.current, rateRef.current)
    stopSources()
    setState((previous) => ({ ...previous, playing: false, currentTime: offsetRef.current }))
  }, [stopSources])

  const toggle = useCallback(() => {
    if (state.playing) pause()
    else void play()
  }, [pause, play, state.playing])

  const seek = useCallback(
    (time: number) => {
      const clamped = Math.max(0, Math.min(time, state.duration))
      offsetRef.current = clamped
      setState((previous) => ({ ...previous, currentTime: clamped }))
      if (state.playing) startAt(clamped)
    },
    [startAt, state.duration, state.playing],
  )

  const setRate = useCallback(
    (rate: number) => {
      rateRef.current = rate
      for (const source of sourcesRef.current.values()) source.playbackRate.value = rate
      // Changing rate mid-flight moves where "now" is, so the clock is rebased
      // on the position that was actually reached.
      const context = contextRef.current
      if (context && state.playing) {
        offsetRef.current = position(context, startedAtRef.current, offsetRef.current, rate)
        startedAtRef.current = context.currentTime
      }
    },
    [state.playing],
  )

  const setStemVolume = useCallback((name: StemName, volume: number) => {
    setMix((previous) => ({ ...previous, [name]: { ...previous[name], volume } }))
  }, [])

  const toggleMute = useCallback((name: StemName) => {
    setMix((previous) => ({
      ...previous,
      [name]: { ...previous[name], muted: !previous[name]?.muted },
    }))
  }, [])

  const toggleSolo = useCallback((name: StemName) => {
    setSolo((previous) => (previous === name ? null : name))
  }, [])

  /**
   * One tap, one whole mix: mute exactly the named stems, unmute the rest,
   * drop any solo. This is what lets "Eu canto" exist as a button instead of
   * five mute taps inside the mixer.
   */
  const applyPreset = useCallback((mutedNames: StemName[]) => {
    setSolo(null)
    setMix((previous) => {
      const next: Record<string, StemMix> = {}
      for (const [name, settings] of Object.entries(previous)) {
        next[name] = { ...settings, muted: mutedNames.includes(name as StemName) }
      }
      return next
    })
  }, [])

  // Position is computed from the audio clock, never from a timer: the audio
  // clock is the one the ear is listening to.
  useEffect(() => {
    const step = () => {
      const context = contextRef.current
      if (context && state.playing) {
        const at = position(context, startedAtRef.current, offsetRef.current, rateRef.current)
        setState((previous) => {
          if (at >= previous.duration && previous.duration > 0) {
            stopSources()
            offsetRef.current = 0
            return { ...previous, playing: false, currentTime: previous.duration }
          }
          return previous.currentTime === at ? previous : { ...previous, currentTime: at }
        })
      }
      frameRef.current = requestAnimationFrame(step)
    }
    frameRef.current = requestAnimationFrame(step)
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    }
  }, [state.playing, stopSources])

  useEffect(() => {
    return () => {
      stopSources()
      void contextRef.current?.close()
      contextRef.current = null
    }
  }, [stopSources])

  return {
    ...state,
    mix,
    solo,
    play,
    pause,
    toggle,
    seek,
    setRate,
    setStemVolume,
    toggleMute,
    toggleSolo,
    applyPreset,
  }
}

function position(context: AudioContext, startedAt: number, offset: number, rate: number): number {
  if (context.currentTime < startedAt) return offset
  return offset + (context.currentTime - startedAt) * rate
}
