import { useCallback, useEffect, useRef, useState } from 'react'

export interface LoopRegion {
  start: number
  end: number
}

export interface PlayerState {
  playing: boolean
  currentTime: number
  duration: number
  ready: boolean
  error: string | null
}

/**
 * Playback control around a plain `<audio>` element.
 *
 * Position is read on an animation frame rather than from `timeupdate`, which
 * only fires a few times a second — far too coarse for a chord grid that has to
 * stay locked to the beat.
 */
export function usePlayer(src: string | null) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const frameRef = useRef<number | null>(null)
  const loopRef = useRef<LoopRegion | null>(null)

  const [state, setState] = useState<PlayerState>({
    playing: false,
    currentTime: 0,
    duration: 0,
    ready: false,
    error: null,
  })

  if (audioRef.current === null && typeof Audio !== 'undefined') {
    audioRef.current = new Audio()
    audioRef.current.preload = 'auto'
  }

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    const onLoaded = () =>
      setState((previous) => ({
        ...previous,
        duration: Number.isFinite(audio.duration) ? audio.duration : 0,
        ready: true,
        error: null,
      }))
    const onPlay = () => setState((previous) => ({ ...previous, playing: true }))
    const onPause = () => setState((previous) => ({ ...previous, playing: false }))
    const onEnded = () => setState((previous) => ({ ...previous, playing: false }))
    const onError = () =>
      setState((previous) => ({ ...previous, error: 'This audio file could not be played', ready: false }))

    audio.addEventListener('loadedmetadata', onLoaded)
    audio.addEventListener('play', onPlay)
    audio.addEventListener('pause', onPause)
    audio.addEventListener('ended', onEnded)
    audio.addEventListener('error', onError)
    return () => {
      audio.removeEventListener('loadedmetadata', onLoaded)
      audio.removeEventListener('play', onPlay)
      audio.removeEventListener('pause', onPause)
      audio.removeEventListener('ended', onEnded)
      audio.removeEventListener('error', onError)
    }
  }, [])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    if (!src) {
      audio.removeAttribute('src')
      audio.load()
      return
    }
    audio.src = src
    audio.load()
    setState((previous) => ({ ...previous, ready: false, currentTime: 0, error: null }))
  }, [src])

  // Position polling plus loop enforcement, both on the same frame so a loop
  // jump never renders a stale playhead.
  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    const step = () => {
      const loop = loopRef.current
      if (loop && audio.currentTime >= loop.end) {
        audio.currentTime = loop.start
      }
      setState((previous) =>
        previous.currentTime === audio.currentTime
          ? previous
          : { ...previous, currentTime: audio.currentTime },
      )
      frameRef.current = requestAnimationFrame(step)
    }
    frameRef.current = requestAnimationFrame(step)
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current)
    }
  }, [])

  useEffect(() => {
    return () => {
      audioRef.current?.pause()
    }
  }, [])

  const play = useCallback(async () => {
    const audio = audioRef.current
    if (!audio) return
    try {
      await audio.play()
    } catch {
      setState((previous) => ({ ...previous, error: 'Playback was blocked by the browser' }))
    }
  }, [])

  const pause = useCallback(() => {
    audioRef.current?.pause()
  }, [])

  const toggle = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) void play()
    else audio.pause()
  }, [play])

  const seek = useCallback((time: number) => {
    const audio = audioRef.current
    if (!audio) return
    const target = Math.max(0, Math.min(time, audio.duration || time))
    audio.currentTime = target
    setState((previous) => ({ ...previous, currentTime: target }))
  }, [])

  const setRate = useCallback((rate: number) => {
    const audio = audioRef.current
    if (!audio) return
    // Keeping the pitch is what makes slowing a song down actually useful for
    // practice; without it everything drops out of tune.
    audio.preservesPitch = true
    audio.playbackRate = rate
  }, [])

  const setVolume = useCallback((volume: number) => {
    if (audioRef.current) audioRef.current.volume = Math.max(0, Math.min(1, volume))
  }, [])

  const setLoop = useCallback((region: LoopRegion | null) => {
    loopRef.current = region
  }, [])

  return { ...state, audioRef, play, pause, toggle, seek, setRate, setVolume, setLoop }
}
