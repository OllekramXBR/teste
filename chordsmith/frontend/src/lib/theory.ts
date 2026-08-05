// Music theory shared by every view: note spelling, transposition, capo logic
// and the chord vocabulary. Mirrors backend/app/analysis/theory.py.

export const SHARP_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
export const FLAT_NAMES = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']

export const QUALITIES: Record<string, number[]> = {
  '': [0, 4, 7],
  m: [0, 3, 7],
  '7': [0, 4, 7, 10],
  m7: [0, 3, 7, 10],
  maj7: [0, 4, 7, 11],
  sus4: [0, 5, 7],
  sus2: [0, 2, 7],
  '6': [0, 4, 7, 9],
  m6: [0, 3, 7, 9],
  dim: [0, 3, 6],
  aug: [0, 4, 8],
  m7b5: [0, 3, 6, 10],
  dim7: [0, 3, 6, 9],
}

/** Human-readable name for each quality, used in tooltips. */
export const QUALITY_LABELS: Record<string, string> = {
  '': 'major',
  m: 'minor',
  '7': 'dominant 7th',
  m7: 'minor 7th',
  maj7: 'major 7th',
  sus4: 'suspended 4th',
  sus2: 'suspended 2nd',
  '6': 'major 6th',
  m6: 'minor 6th',
  dim: 'diminished',
  aug: 'augmented',
  m7b5: 'half-diminished',
  dim7: 'diminished 7th',
}

const FLAT_MAJOR_TONICS = new Set([5, 10, 3, 8, 1, 6])
const FLAT_MINOR_TONICS = new Set([2, 7, 0, 5, 10, 3])

export const NO_CHORD = 'N'

export function mod12(value: number): number {
  return ((value % 12) + 12) % 12
}

export function noteName(pitchClass: number, useFlats = false): string {
  return (useFlats ? FLAT_NAMES : SHARP_NAMES)[mod12(pitchClass)]
}

export function keyUsesFlats(tonic: number, mode: string): boolean {
  return mode === 'minor' ? FLAT_MINOR_TONICS.has(mod12(tonic)) : FLAT_MAJOR_TONICS.has(mod12(tonic))
}

export interface ParsedChord {
  root: number
  quality: string
}

export function parseLabel(label: string): ParsedChord | null {
  const trimmed = label.trim()
  if (!trimmed || trimmed === NO_CHORD) return null
  const rootLength = trimmed.length > 1 && (trimmed[1] === '#' || trimmed[1] === 'b') ? 2 : 1
  const rootName = trimmed.slice(0, rootLength)
  const quality = trimmed.slice(rootLength)
  if (!(quality in QUALITIES)) return null
  for (let pc = 0; pc < 12; pc += 1) {
    if (SHARP_NAMES[pc] === rootName || FLAT_NAMES[pc] === rootName) {
      return { root: pc, quality }
    }
  }
  return null
}

export function formatChord(root: number, quality: string, useFlats = false): string {
  return `${noteName(root, useFlats)}${quality}`
}

export function transposeLabel(label: string, semitones: number, useFlats = false): string {
  if (!label || label === NO_CHORD) return label
  const parsed = parseLabel(label)
  if (!parsed) return label
  return formatChord(parsed.root + semitones, parsed.quality, useFlats)
}

/**
 * The chord shape a player fingers when a capo sits on `capoFret`.
 *
 * A capo raises the pitch of everything behind it, so to keep a chord sounding
 * the same the shape must be transposed *down* by the fret number. The song's
 * key never changes — only what your left hand does.
 */
export function capoShape(label: string, capoFret: number, useFlats = false): string {
  if (capoFret === 0) return label
  return transposeLabel(label, -capoFret, useFlats)
}

export function chordPitchClasses(root: number, quality: string): number[] {
  return (QUALITIES[quality] ?? QUALITIES['']).map((interval) => mod12(root + interval))
}

/** Intervals present in the chord, as scale-degree names for the diagram legend. */
export function intervalNames(quality: string): string[] {
  const names: Record<number, string> = {
    0: 'R',
    2: '2',
    3: 'b3',
    4: '3',
    5: '4',
    6: 'b5',
    7: '5',
    8: '#5',
    9: '6',
    10: 'b7',
    11: '7',
  }
  return (QUALITIES[quality] ?? QUALITIES['']).map((interval) => names[interval] ?? `${interval}`)
}

/** Roman-numeral position of a chord within a key, or null when it is borrowed. */
export function romanNumeral(root: number, quality: string, tonic: number, mode: string): string | null {
  const steps = mode === 'minor' ? [0, 2, 3, 5, 7, 8, 10] : [0, 2, 4, 5, 7, 9, 11]
  const degree = steps.indexOf(mod12(root - tonic))
  if (degree < 0) return null
  const numerals = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII']
  const isMinorish = quality.startsWith('m') && quality !== 'maj7'
  const numeral = isMinorish || quality === 'dim' ? numerals[degree].toLowerCase() : numerals[degree]
  const suffix = quality === 'dim' || quality === 'dim7' ? '°' : quality === 'm7b5' ? 'ø' : ''
  return numeral + suffix
}

export const ALL_KEYS = Array.from({ length: 12 }, (_, index) => index)
