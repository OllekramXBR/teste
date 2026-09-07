// Brazilian chord spelling, mirroring `backend/app/analysis/cifra.py`.
//
// The two files exist because the same chart is written in two places — the
// server renders the printable cifra, the browser labels the diagrams — and a
// chord that is called G7M on paper and Gmaj7 on screen is a bug the reader has
// to work around. The mapping is small enough to duplicate and important enough
// to keep identical; the backend tests pin its half.

import { parseLabel, SHARP_NAMES, FLAT_NAMES } from './theory'

export const BR_QUALITY: Record<string, string> = {
  '': '',
  m: 'm',
  '7': '7',
  m7: 'm7',
  maj7: '7M',
  sus4: 'sus4',
  sus2: 'sus2',
  '6': '6',
  m6: 'm6',
  dim: '°',
  aug: '+',
  m7b5: 'm7(b5)',
  dim7: '°7',
}

// What each quality becomes when the chart is simplified, mirroring
// `SIMPLE_QUALITY` in cifra.py. A chroma decoder hears a passing melody note as
// an added sixth or a suspended fourth; each call is defensible frame by frame
// while being wrong about the song, and a verse with a dozen symbols is one the
// reader stops trusting. Diminished and augmented survive: a player really does
// finger those differently.
export const SIMPLE_QUALITY: Record<string, string> = {
  '': '',
  m: 'm',
  '7': '',
  m7: 'm',
  maj7: '',
  sus4: '',
  sus2: '',
  '6': '',
  m6: 'm',
  dim: 'dim',
  aug: 'aug',
  m7b5: 'm',
  dim7: 'dim',
}

/** Reduce a chord label to the triad a hand actually makes. */
export function simplify(label: string, useFlats = false): string {
  const parsed = parseLabel(label)
  if (!parsed) return label
  const names = useFlats ? FLAT_NAMES : SHARP_NAMES
  return `${names[parsed.root]}${SIMPLE_QUALITY[parsed.quality] ?? parsed.quality}`
}

/** Rewrite one chord label in Brazilian notation; unknown labels pass through. */
export function br(label: string, useFlats = false): string {
  const parsed = parseLabel(label)
  if (!parsed) return label
  const names = useFlats ? FLAT_NAMES : SHARP_NAMES
  return `${names[parsed.root]}${BR_QUALITY[parsed.quality] ?? parsed.quality}`
}
