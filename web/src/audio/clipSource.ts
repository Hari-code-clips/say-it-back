// A stored answer clip played into an answer window instead of the microphone (endpoint 24, "Use the sample answer").
// It hands the same 20 ms, 640-byte chunks the mic does, at real-time pace, so the Live socket gets the audio as it would
// from a person and the capture keeps exactly what was sent as that question's WAV. Turn mode records it the same way.
import { rms } from './endpoint.ts'
import type { ChunkSink, ChunkSource } from './source.ts'
import { MIC_RATE } from './wav.ts'

/** 20 ms at 16 kHz: the mic's chunk (640 bytes). */
export const CHUNK_SAMPLES = MIC_RATE / 50
const CHUNK_MS = 20

/** The clock the clip is paced on. Real time in the app; a fake one in tests. */
export interface ClipClock {
  now(): number
  /** Call `fn` every `ms` until the returned function is called. */
  every(ms: number, fn: () => void): () => void
}

export const realClock: ClipClock = {
  now: () => performance.now(),
  every: (ms, fn) => {
    const id = setInterval(fn, ms)
    return () => clearInterval(id)
  },
}

export interface ClipSourceOptions {
  /** Silence sent after the clip, so the answer ends the way a spoken one does. Default 600 ms. */
  tailMs?: number
  clock?: ClipClock
  /** A timer tick that came late sends what is due, but at most this many chunks at once. Default 10 (200 ms). */
  maxBurst?: number
}

export class ClipSource implements ChunkSource {
  /** Resolves once the whole clip and its tail have been handed over. */
  readonly done: Promise<void>
  private readonly pcm: Int16Array
  private readonly total: number
  private readonly clock: ClipClock
  private readonly maxBurst: number
  private sink: ChunkSink | null = null
  private sent = 0
  private startedAt = 0
  private sentAtStart = 0
  private stopTimer: (() => void) | null = null
  private finished = false
  private resolveDone!: () => void
  private lastLevel = 0

  constructor(pcm: Int16Array, opts: ClipSourceOptions = {}) {
    this.pcm = pcm
    this.clock = opts.clock ?? realClock
    this.maxBurst = opts.maxBurst ?? 10
    const tailChunks = Math.ceil((opts.tailMs ?? 600) / CHUNK_MS)
    this.total = Math.ceil(pcm.length / CHUNK_SAMPLES) + tailChunks
    this.done = new Promise((resolve) => {
      this.resolveDone = resolve
    })
  }

  /** Chunks handed over so far. */
  get chunksSent(): number {
    return this.sent
  }

  get level(): number {
    return this.finished || !this.sink ? 0 : Math.min(1, this.lastLevel * 5)
  }

  setSink(sink: ChunkSink | null): void {
    this.sink = sink
    if (sink && !this.stopTimer && !this.finished) {
      // Pace from now: the first chunk at once, then one every 20 ms of the clock.
      this.startedAt = this.clock.now()
      this.sentAtStart = this.sent
      this.emit(1)
      this.stopTimer = this.clock.every(CHUNK_MS, () => this.tick())
    } else if (!sink) {
      this.stopTimer?.()
      this.stopTimer = null
    }
  }

  private tick(): void {
    const due = this.sentAtStart + Math.floor((this.clock.now() - this.startedAt) / CHUNK_MS) + 1
    this.emit(Math.min(this.maxBurst, due - this.sent))
  }

  private emit(count: number): void {
    for (let i = 0; i < count && this.sink && this.sent < this.total; i++) {
      const from = this.sent * CHUNK_SAMPLES
      const chunk = new Int16Array(CHUNK_SAMPLES) // the last clip chunk and the tail are padded with silence
      if (from < this.pcm.length) chunk.set(this.pcm.subarray(from, Math.min(this.pcm.length, from + CHUNK_SAMPLES)))
      this.sent++
      this.lastLevel = rms(chunk)
      this.sink(chunk)
    }
    if (this.sent >= this.total && !this.finished) {
      this.finished = true
      this.stopTimer?.()
      this.stopTimer = null
      this.resolveDone()
    }
  }
}
