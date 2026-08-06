// Thin client for the Metatron API.

export interface BeatEvent {
  index: number
  time: number
  duration: number
  bar: number
  beatInBar: number
  downbeat: boolean
  root: number | null
  quality: string
  label: string
  notes: number[]
  confidence: number
}

export interface ChordSpan {
  label: string
  root: number | null
  quality: string
  notes: number[]
  start: number
  end: number
  startBeat: number
  endBeat: number
  confidence: number
}

export interface LeadNote {
  start: number
  end: number
  midi: number
  name: string
  /** Null when the note falls outside the guitar's range. */
  string: number | null
  fret: number | null
  beat: number
  bar: number
  confidence: number
  velocity: number
}

export interface LeadSection {
  startBar: number
  endBar: number
  start: number
  end: number
  noteCount: number
  notesPerBar: number
  lowMidi: number
  highMidi: number
  lowName: string
  highName: string
  /** Dense and wide-ranging enough to read as an instrumental solo. */
  isSolo: boolean
}

export interface Lead {
  tuning: number[]
  stringNames: string[]
  coverage: number
  notes: LeadNote[]
  sections: LeadSection[]
}

export interface Analysis {
  duration: number
  bpm: number
  beatsPerBar: number
  key: { tonic: number; mode: string; name: string; confidence: number }
  useFlats: boolean
  beats: BeatEvent[]
  chords: ChordSpan[]
  uniqueChords: string[]
  lead: Lead
  analysisSeconds: number
}

export interface LyricWord {
  text: string
  start: number
  end: number
  probability: number
}

export interface LyricSegment {
  start: number
  end: number
  text: string
}

export interface Lyrics {
  language: string
  languageProbability: number
  model: string
  words: LyricWord[]
  segments: LyricSegment[]
  wordCount: number
  audioSeconds: number
  transcribeSeconds?: number
  /** True once a person has corrected it; the model no longer overwrites it. */
  edited?: boolean
}

/** Stems are produced together, so one status covers the whole set. */
export type StemName = 'lead' | 'backing' | 'drums' | 'bass' | 'other'

export interface Stem {
  name: StemName
  label: string
  url: string
  bytes: number
}

export type JobStatus = 'none' | 'pending' | 'transcribing' | 'separating' | 'ready' | 'failed'

export type SongStatus = 'pending' | 'analyzing' | 'ready' | 'failed'

export interface Song {
  id: string
  title: string
  artist: string
  originalName: string
  contentType: string
  sizeBytes: number
  status: SongStatus
  error: string | null
  duration: number | null
  bpm: number | null
  keyName: string | null
  createdAt: string
  updatedAt: string
  audioUrl: string
  lyricsStatus: JobStatus
  lyricsError: string | null
  stemsStatus: JobStatus
  stemsError: string | null
  analysis?: Analysis | null
  lyrics?: Lyrics | null
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      // Non-JSON error body; the status-based message is the best we have.
    }
    throw new ApiError(detail, response.status)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export function listSongs(search = ''): Promise<{ songs: Song[] }> {
  const query = search ? `?search=${encodeURIComponent(search)}` : ''
  return request(`/api/songs${query}`)
}

export function getSong(id: string): Promise<Song> {
  return request(`/api/songs/${id}`)
}

export function deleteSong(id: string): Promise<void> {
  return request(`/api/songs/${id}`, { method: 'DELETE' })
}

export function reanalyze(id: string): Promise<Song> {
  return request(`/api/songs/${id}/reanalyze`, { method: 'POST' })
}

export interface UploadFields {
  title?: string
  artist?: string
}

export function uploadSong(
  file: File,
  fields: UploadFields = {},
  onProgress?: (fraction: number) => void,
): Promise<Song> {
  // XHR rather than fetch: upload progress events are the whole point here, and
  // fetch still cannot report them.
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)
    if (fields.title) form.append('title', fields.title)
    if (fields.artist) form.append('artist', fields.artist)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/songs')
    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable && onProgress) onProgress(event.loaded / event.total)
    })
    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText) as Song)
        return
      }
      let detail = `Upload failed with status ${xhr.status}`
      try {
        const parsed = JSON.parse(xhr.responseText)
        if (typeof parsed?.detail === 'string') detail = parsed.detail
      } catch {
        // Keep the status-based message.
      }
      reject(new ApiError(detail, xhr.status))
    })
    xhr.addEventListener('error', () => reject(new ApiError('Network error during upload', 0)))
    xhr.addEventListener('abort', () => reject(new ApiError('Upload cancelled', 0)))
    xhr.send(form)
  })
}

export function midiUrl(id: string, transpose = 0): string {
  return `/api/songs/${id}/midi?transpose=${transpose}`
}

export interface CifraOptions {
  transpose?: number
  capo?: number
  simplify?: boolean
  download?: boolean
}

export function cifraUrl(id: string, options: CifraOptions = {}): string {
  const query = new URLSearchParams({
    transpose: String(options.transpose ?? 0),
    capo: String(options.capo ?? 0),
    simplify: String(options.simplify ?? true),
  })
  if (options.download) query.set('download', 'true')
  return `/api/songs/${id}/cifra?${query}`
}

export async function getCifra(id: string, options: CifraOptions = {}): Promise<string> {
  const response = await fetch(cifraUrl(id, options))
  if (!response.ok) throw new ApiError('The cifra could not be built', response.status)
  return response.text()
}

export function transcribeLyrics(id: string): Promise<Song> {
  return request(`/api/songs/${id}/lyrics`, { method: 'POST' })
}

export function getLyrics(id: string): Promise<{
  status: JobStatus
  error: string | null
  lyrics: Lyrics | null
}> {
  return request(`/api/songs/${id}/lyrics`)
}

export function editLyrics(id: string, segments: LyricSegment[]): Promise<{ lyrics: Lyrics }> {
  return request(`/api/songs/${id}/lyrics`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ segments }),
  })
}

export interface LibraryEntry {
  name: string
  path: string
  isDir: boolean
  bytes: number
}

export function browseLibrary(path = ''): Promise<{
  enabled: boolean
  path: string
  parent: string | null
  entries: LibraryEntry[]
}> {
  return request(`/api/library?path=${encodeURIComponent(path)}`)
}

export function importFromLibrary(path: string, artist = ''): Promise<Song> {
  return request('/api/songs/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, artist }),
  })
}

export interface AuthUser {
  id: string
  username: string
  displayName: string
}

export interface AuthState {
  user: AuthUser | null
  /** True when the server refuses API calls without a session. */
  required: boolean
  hasUsers: boolean
}

export function getAuthState(): Promise<AuthState> {
  return request('/api/auth/me')
}

export function login(username: string, password: string): Promise<{ user: AuthUser }> {
  return request('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export function register(username: string, password: string): Promise<{ user: AuthUser }> {
  return request('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export function listUsers(): Promise<{ users: AuthUser[] }> {
  return request('/api/auth/users')
}

export function updateProfile(displayName: string): Promise<{ user: AuthUser }> {
  return request('/api/auth/me', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ displayName }),
  })
}

export function changePassword(current: string, replacement: string): Promise<void> {
  return request('/api/auth/password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ current, replacement }),
  })
}

export function logout(): Promise<void> {
  return request('/api/auth/logout', { method: 'POST' })
}

export function setSharing(id: string, shared: boolean): Promise<Song> {
  return request(`/api/songs/${id}/sharing`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ shared }),
  })
}

export interface Variant {
  key: string
  stems: StemName[]
}

export function renderVariant(
  id: string,
  semitones: number,
  rate = 1,
): Promise<{ key: string; status: 'ready' | 'rendering' }> {
  return request(`/api/songs/${id}/variants?semitones=${semitones}&rate=${rate}`, {
    method: 'POST',
  })
}

export function listVariants(id: string): Promise<{ variants: Variant[] }> {
  return request(`/api/songs/${id}/variants`)
}

/** Key for a rendered combination; mirrors `variants.variant_key` on the server. */
export function variantKey(semitones: number, rate = 1): string {
  const sign = semitones < 0 ? 'm' : 'p'
  return `t${sign}${Math.abs(semitones)}_r${Math.round(rate * 100)}`
}

export function variantStemUrl(id: string, key: string, stem: StemName): string {
  return `/api/songs/${id}/variants/${key}/${stem}`
}

export interface TranscribedTrack {
  name: string
  program: number
  /** Which separated stem this was transcribed from. */
  stem?: string
  notes: {
    midi: number
    start: number
    end: number
    velocity: number
    string?: number | null
    fret?: number | null
  }[]
}

export function stemsZipUrl(id: string): string {
  return `/api/songs/${id}/stems.zip`
}

export function getTracks(id: string): Promise<{
  status: 'none' | 'pending' | 'ready'
  tracks: TranscribedTrack[]
}> {
  return request(`/api/songs/${id}/tracks`)
}

export function midiMultitrackUrl(id: string, transpose = 0): string {
  return `/api/songs/${id}/midi?tracks=multi&transpose=${transpose}`
}

export function separateAll(): Promise<{ queued: number; songs: string[] }> {
  return request('/api/songs/stems/all', { method: 'POST' })
}

export function separateStems(id: string): Promise<Song> {
  return request(`/api/songs/${id}/stems`, { method: 'POST' })
}

export function getStems(id: string): Promise<{
  status: JobStatus
  error: string | null
  stems: Stem[]
}> {
  return request(`/api/songs/${id}/stems`)
}

export function deleteStems(id: string): Promise<void> {
  return request(`/api/songs/${id}/stems`, { method: 'DELETE' })
}

export interface SetlistSummary {
  id: string
  name: string
  notes: string
  songCount: number
  createdAt: string
  updatedAt: string
}

export interface Setlist extends Omit<SetlistSummary, 'songCount'> {
  songs: Song[]
}

export function listSetlists(): Promise<{ setlists: SetlistSummary[] }> {
  return request('/api/setlists')
}

export function getSetlist(id: string): Promise<Setlist> {
  return request(`/api/setlists/${id}`)
}

export function createSetlist(name: string): Promise<Setlist> {
  return request('/api/setlists', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

export function setSetlistSongs(id: string, songs: string[]): Promise<Setlist> {
  return request(`/api/setlists/${id}/songs`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ songs }),
  })
}

export function deleteSetlist(id: string): Promise<void> {
  return request(`/api/setlists/${id}`, { method: 'DELETE' })
}

export interface Health {
  status: string
  songs: number
  analyzing: number
  storedBytes: number
  maxUploadBytes: number
  supportedFormats: string[]
}

export function getHealth(): Promise<Health> {
  return request('/api/health')
}
