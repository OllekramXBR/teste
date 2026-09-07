// Fingering generation for fretted instruments.
//
// Rather than shipping a hand-written table of a few hundred shapes, voicings
// are searched for on the fly: for every position on the neck, enumerate what
// each string could play, then score the candidates on playability. This covers
// the entire chord vocabulary in every key without a lookup table to maintain.

import { chordPitchClasses, mod12 } from './theory'

export interface Instrument {
  id: 'guitar' | 'ukulele' | 'cavaquinho' | 'viola' | 'bass' | 'mandolin' | 'banjo'
  name: string
  /** MIDI note of each open string, in string order (not pitch order). */
  tuning: number[]
  stringNames: string[]
  frets: number
  /**
   * True when the strings are not in ascending pitch order. On a re-entrant
   * instrument the lowest-pitched string is not the bass the listener hears, so
   * root-position scoring does not apply.
   */
  reentrant: boolean
}

export const GUITAR: Instrument = {
  id: 'guitar',
  name: 'Violão',
  tuning: [40, 45, 50, 55, 59, 64], // E2 A2 D3 G3 B3 E4
  stringNames: ['E', 'A', 'D', 'G', 'B', 'e'],
  frets: 15,
  reentrant: false,
}

export const UKULELE: Instrument = {
  id: 'ukulele',
  name: 'Ukulele',
  tuning: [67, 60, 64, 69], // G4 C4 E4 A4 — the G string sits above the C
  stringNames: ['G', 'C', 'E', 'A'],
  frets: 12,
  reentrant: true,
}

// The search does not care what it is fingering, so a new instrument is a
// tuning and nothing else — no shapes to draw, no table to maintain. Which is
// why the two that matter here and appear in almost no chord site, the
// cavaquinho and the viola caipira, cost the same as the ones that do.
export const CAVAQUINHO: Instrument = {
  id: 'cavaquinho',
  name: 'Cavaquinho',
  tuning: [62, 67, 71, 74], // D4 G4 B4 D5
  stringNames: ['D', 'G', 'B', 'D'],
  frets: 15,
  reentrant: false,
}

export const VIOLA_CAIPIRA: Instrument = {
  id: 'viola',
  name: 'Viola caipira',
  // Cebolão em Mi, the most common Brazilian tuning; each course is drawn as a
  // single string because both strings of a course are fingered together.
  tuning: [47, 52, 56, 59, 64], // B2 E3 G#3 B3 E4
  stringNames: ['B', 'E', 'G#', 'B', 'E'],
  frets: 15,
  reentrant: false,
}

export const BASS: Instrument = {
  id: 'bass',
  name: 'Baixo',
  tuning: [28, 33, 38, 43], // E1 A1 D2 G2
  stringNames: ['E', 'A', 'D', 'G'],
  frets: 15,
  reentrant: false,
}

export const MANDOLIN: Instrument = {
  id: 'mandolin',
  name: 'Bandolim',
  tuning: [55, 62, 69, 76], // G3 D4 A4 E5
  stringNames: ['G', 'D', 'A', 'E'],
  frets: 15,
  reentrant: false,
}

export const BANJO: Instrument = {
  id: 'banjo',
  name: 'Banjo',
  // Open G. The fifth string is a high drone that sits beside the lowest one,
  // so the set is re-entrant and root-in-the-bass scoring does not apply.
  tuning: [67, 50, 55, 59, 62], // G4 D3 G3 B3 D4
  stringNames: ['G', 'D', 'G', 'B', 'D'],
  frets: 15,
  reentrant: true,
}

export const INSTRUMENTS: Record<Instrument['id'], Instrument> = {
  guitar: GUITAR,
  ukulele: UKULELE,
  cavaquinho: CAVAQUINHO,
  viola: VIOLA_CAIPIRA,
  bass: BASS,
  mandolin: MANDOLIN,
  banjo: BANJO,
}

/** `-1` means the string is muted; `0` is open; any other number is a fret. */
export type Voicing = number[]

export interface Fingering {
  frets: Voicing
  /** Lowest fretted fret in the shape, used to draw the position marker. */
  baseFret: number
  /** Fret that has to be barred, or 0 when no barre is needed. */
  barre: number
  score: number
}

const MAX_SPAN = 4 // frets a hand can comfortably cover

function candidatesForString(
  openNote: number,
  chordTones: number[],
  windowStart: number,
  windowEnd: number,
): number[] {
  const options: number[] = [-1] // muting is always allowed
  if (chordTones.includes(mod12(openNote))) options.push(0)
  for (let fret = Math.max(windowStart, 1); fret <= windowEnd; fret += 1) {
    if (chordTones.includes(mod12(openNote + fret))) options.push(fret)
  }
  return options
}

/**
 * Reject shapes that need a barre across a string the voicing wants open.
 *
 * When the lowest fretted fret is held on more than one string, one finger has
 * to lie across them — and that finger also stops every string in between. Any
 * open string caught inside that span would in reality be fretted, so the shape
 * cannot be played as written.
 */
function requiresImpossibleBarre(voicing: Voicing): boolean {
  const fretted = voicing.filter((fret) => fret > 0)
  if (!fretted.length) return false
  const lowest = Math.min(...fretted)
  const held = voicing
    .map((fret, index) => (fret === lowest ? index : -1))
    .filter((index) => index >= 0)
  if (held.length < 2) return false
  const [first, last] = [held[0], held[held.length - 1]]
  return voicing.some((fret, index) => fret === 0 && index > first && index < last)
}

function scoreVoicing(
  voicing: Voicing,
  instrument: Instrument,
  root: number,
  chordTones: number[],
): number | null {
  const { tuning, reentrant } = instrument
  const sounding = voicing
    .map((fret, index) => (fret < 0 ? null : tuning[index] + fret))
    .filter((note): note is number => note !== null)

  if (sounding.length < Math.min(3, tuning.length)) return null

  const covered = new Set(sounding.map(mod12))
  // Every chord tone must be present, otherwise it is a different chord.
  for (const tone of chordTones) {
    if (!covered.has(tone)) return null
  }

  if (requiresImpossibleBarre(voicing)) return null

  // Muted strings in the middle of the shape are awkward and sound gappy.
  const firstSounding = voicing.findIndex((fret) => fret >= 0)
  const lastSounding = voicing.length - 1 - [...voicing].reverse().findIndex((fret) => fret >= 0)
  let innerMutes = 0
  for (let index = firstSounding; index <= lastSounding; index += 1) {
    if (voicing[index] < 0) innerMutes += 1
  }

  const fretted = voicing.filter((fret) => fret > 0)
  const span = fretted.length ? Math.max(...fretted) - Math.min(...fretted) : 0
  if (span > MAX_SPAN) return null

  // How far up the neck the hand has to sit.
  const position = fretted.length ? Math.min(...fretted) : 0

  let score = 0
  score += sounding.length * 2.5 // fuller chords sound better
  score += voicing.filter((fret) => fret === 0).length * 1.2 // open strings ring
  score -= innerMutes * 5
  score -= span * 1.4
  score -= new Set(fretted).size * 0.4 // fewer distinct fingers is easier
  score -= position * 0.55 // prefer shapes near the nut

  // On a re-entrant instrument the lowest-pitched string is not the bass the
  // listener hears, so root-position scoring would be meaningless. Elsewhere a
  // chord voiced over the wrong bass note is a different chord (D/F#, not D),
  // which is penalised rather than merely left unrewarded.
  if (!reentrant) {
    score += mod12(Math.min(...sounding)) === root ? 4 : -3
  }
  return score
}

function detectBarre(voicing: Voicing): number {
  const fretted = voicing.filter((fret) => fret > 0)
  if (!fretted.length) return 0
  const lowest = Math.min(...fretted)
  const onLowest = voicing.filter((fret) => fret === lowest).length
  // A barre is only worth drawing when the low fret is held on several strings
  // and nothing below it is played open.
  const hasOpenStrings = voicing.some((fret) => fret === 0)
  return onLowest >= 2 && !hasOpenStrings ? lowest : 0
}

/**
 * Best fingerings for a chord on an instrument, highest-scoring first.
 * Returns an empty array when the chord is unplayable (never happens for the
 * shipped vocabulary, but callers should not assume).
 */
export function findFingerings(
  root: number,
  quality: string,
  instrument: Instrument,
  limit = 3,
): Fingering[] {
  const chordTones = chordPitchClasses(root, quality)
  const found: Fingering[] = []
  const seen = new Set<string>()

  for (let windowStart = 0; windowStart <= instrument.frets - MAX_SPAN; windowStart += 1) {
    const windowEnd = windowStart + MAX_SPAN
    const perString = instrument.tuning.map((open) =>
      candidatesForString(open, chordTones, windowStart, windowEnd),
    )

    const voicing: Voicing = new Array(instrument.tuning.length).fill(-1)
    const walk = (stringIndex: number): void => {
      if (stringIndex === instrument.tuning.length) {
        const score = scoreVoicing(voicing, instrument, root, chordTones)
        if (score === null) return
        const signature = voicing.join(',')
        if (seen.has(signature)) return
        seen.add(signature)
        const fretted = voicing.filter((fret) => fret > 0)
        found.push({
          frets: [...voicing],
          baseFret: fretted.length ? Math.min(...fretted) : 1,
          barre: detectBarre(voicing),
          score,
        })
        return
      }
      for (const fret of perString[stringIndex]) {
        voicing[stringIndex] = fret
        walk(stringIndex + 1)
      }
      voicing[stringIndex] = -1
    }
    walk(0)
  }

  found.sort((a, b) => b.score - a.score)
  return found.slice(0, limit)
}

const fingeringCache = new Map<string, Fingering[]>()

/** Memoised wrapper — the search is cheap but runs on every chord render. */
export function getFingerings(
  root: number,
  quality: string,
  instrument: Instrument,
  limit = 3,
): Fingering[] {
  const cacheKey = `${instrument.id}:${root}:${quality}:${limit}`
  const cached = fingeringCache.get(cacheKey)
  if (cached) return cached
  const result = findFingerings(root, quality, instrument, limit)
  fingeringCache.set(cacheKey, result)
  return result
}

/** MIDI notes a voicing actually sounds, for previewing a shape. */
export function voicingNotes(voicing: Voicing, instrument: Instrument): number[] {
  return voicing
    .map((fret, index) => (fret < 0 ? null : instrument.tuning[index] + fret))
    .filter((note): note is number => note !== null)
}
