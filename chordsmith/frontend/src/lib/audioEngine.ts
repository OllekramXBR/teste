// Web Audio synthesis for the chord track and the metronome.
//
// Both are scheduled ahead of the audio element's clock rather than fired from
// React state, because timer callbacks are far too jittery to sound musical.
// The engine keeps a short lookahead window and only ever schedules events that
// have not been scheduled before.

export type InstrumentVoice = 'guitar' | 'piano' | 'ukulele'

const LOOKAHEAD_SECONDS = 0.35
const TICK_INTERVAL_MS = 60

function midiToHz(midi: number): number {
  return 440 * Math.pow(2, (midi - 69) / 12)
}

export class AudioEngine {
  private context: AudioContext | null = null
  private chordGain: GainNode | null = null
  private clickGain: GainNode | null = null
  private scheduled = new Set<string>()
  private timer: number | null = null
  private chordVolume = 0.0
  private clickVolume = 0.0

  /** Lazily create the context; browsers require a user gesture first. */
  private ensureContext(): AudioContext {
    if (!this.context) {
      const Ctor: typeof AudioContext =
        window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      this.context = new Ctor()
      this.chordGain = this.context.createGain()
      this.chordGain.gain.value = this.chordVolume
      this.chordGain.connect(this.context.destination)
      this.clickGain = this.context.createGain()
      this.clickGain.gain.value = this.clickVolume
      this.clickGain.connect(this.context.destination)
    }
    return this.context
  }

  async resume(): Promise<void> {
    const context = this.ensureContext()
    if (context.state === 'suspended') await context.resume()
  }

  setChordVolume(volume: number): void {
    this.chordVolume = volume
    if (this.chordGain && this.context) {
      this.chordGain.gain.setTargetAtTime(volume, this.context.currentTime, 0.02)
    }
  }

  setClickVolume(volume: number): void {
    this.clickVolume = volume
    if (this.clickGain && this.context) {
      this.clickGain.gain.setTargetAtTime(volume, this.context.currentTime, 0.02)
    }
  }

  get currentTime(): number {
    return this.context?.currentTime ?? 0
  }

  /** Drop every pending schedule, e.g. after a seek or a loop jump. */
  reset(): void {
    this.scheduled.clear()
  }

  /**
   * Play a chord as a short arpeggiated cluster.
   * `notes` are MIDI numbers; `when` is an AudioContext timestamp.
   */
  playChord(notes: number[], when: number, voice: InstrumentVoice = 'guitar', duration = 0.9): void {
    const context = this.ensureContext()
    if (!this.chordGain || this.chordVolume <= 0) return

    const strum = voice === 'piano' ? 0.004 : 0.022
    notes.forEach((midi, index) => {
      const start = when + index * strum
      const oscillator = context.createOscillator()
      const gain = context.createGain()
      oscillator.type = voice === 'piano' ? 'triangle' : 'sawtooth'
      oscillator.frequency.value = midiToHz(midi)

      const filter = context.createBiquadFilter()
      filter.type = 'lowpass'
      filter.frequency.value = voice === 'piano' ? 2600 : 1900
      filter.Q.value = 0.7

      const peak = 0.22 / Math.max(notes.length, 1)
      gain.gain.setValueAtTime(0, start)
      gain.gain.linearRampToValueAtTime(peak, start + 0.012)
      gain.gain.exponentialRampToValueAtTime(0.0001, start + duration)

      oscillator.connect(filter)
      filter.connect(gain)
      gain.connect(this.chordGain!)
      oscillator.start(start)
      oscillator.stop(start + duration + 0.05)
    })
  }

  /** Metronome click; accented clicks mark the downbeat. */
  playClick(when: number, accented = false): void {
    const context = this.ensureContext()
    if (!this.clickGain || this.clickVolume <= 0) return

    const oscillator = context.createOscillator()
    const gain = context.createGain()
    oscillator.type = 'square'
    oscillator.frequency.value = accented ? 1600 : 1100
    gain.gain.setValueAtTime(0, when)
    gain.gain.linearRampToValueAtTime(accented ? 0.5 : 0.28, when + 0.002)
    gain.gain.exponentialRampToValueAtTime(0.0001, when + 0.05)
    oscillator.connect(gain)
    gain.connect(this.clickGain)
    oscillator.start(when)
    oscillator.stop(when + 0.06)
  }

  /**
   * Start the scheduling loop. `provider` is polled on every tick and returns
   * the events due soon plus the offset between song time and audio time.
   */
  start(
    provider: () => {
      chords: { key: string; time: number; notes: number[]; voice: InstrumentVoice }[]
      clicks: { key: string; time: number; accented: boolean }[]
      audioTimeOffset: number
    },
  ): void {
    this.ensureContext()
    this.stop()
    const tick = () => {
      const { chords, clicks, audioTimeOffset } = provider()
      const horizon = this.currentTime + LOOKAHEAD_SECONDS
      for (const chord of chords) {
        const at = chord.time + audioTimeOffset
        if (this.scheduled.has(chord.key) || at < this.currentTime || at > horizon) continue
        this.scheduled.add(chord.key)
        this.playChord(chord.notes, at, chord.voice)
      }
      for (const click of clicks) {
        const at = click.time + audioTimeOffset
        if (this.scheduled.has(click.key) || at < this.currentTime || at > horizon) continue
        this.scheduled.add(click.key)
        this.playClick(at, click.accented)
      }
      // The set would grow without bound over a long session.
      if (this.scheduled.size > 2000) this.scheduled.clear()
    }
    this.timer = window.setInterval(tick, TICK_INTERVAL_MS)
    tick()
  }

  stop(): void {
    if (this.timer !== null) {
      window.clearInterval(this.timer)
      this.timer = null
    }
  }

  dispose(): void {
    this.stop()
    void this.context?.close()
    this.context = null
    this.chordGain = null
    this.clickGain = null
  }
}

/**
 * Voice a chord for playback: root in the bass, remaining tones stacked above
 * middle C so successive chords stay in a similar register.
 */
export function voiceChord(root: number, notes: number[], octave = 4): number[] {
  if (notes.length === 0) return []
  const base = 12 * (octave + 1) + root
  const voiced = [base - 24]
  let previous = base
  voiced.push(previous)
  for (const note of notes.slice(1)) {
    let pitch = 12 * (octave + 1) + note
    while (pitch <= previous) pitch += 12
    voiced.push(pitch)
    previous = pitch
  }
  return voiced
}
