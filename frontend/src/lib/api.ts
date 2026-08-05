// Thin client for the Chordsmith API.

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

export interface Analysis {
  duration: number
  bpm: number
  beatsPerBar: number
  key: { tonic: number; mode: string; name: string; confidence: number }
  useFlats: boolean
  beats: BeatEvent[]
  chords: ChordSpan[]
  uniqueChords: string[]
  analysisSeconds: number
}

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
  analysis?: Analysis | null
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
