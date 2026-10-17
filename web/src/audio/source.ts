// Where an answer window's 16 kHz PCM comes from. The microphone (mic.ts) is the usual source; a stored sample answer
// (clipSource.ts) is the other. captureAnswer() only needs this surface, so both feed the same capture, the same Live
// socket send and the same WAV for POST /check.

/** Receives 20 ms chunks of 16 kHz mono PCM16 (320 samples, 640 bytes), in order. */
export type ChunkSink = (chunk: Int16Array) => void

export interface ChunkSource {
  /** Route chunks to one consumer, or null to stop. Only one consumer at a time. */
  setSink(sink: ChunkSink | null): void
  /** Smoothed level, 0..1, for the orb. */
  readonly level: number
}

/**
 * One stream, two consumers: the main sink (an answer window) and a side sink (the worker's problem report, endpoint 21).
 * A chunk goes to the main sink when one is set, and to the side sink only when none is: a report recorded during the
 * briefing never takes in an answer, and an answer never loses a chunk to a report.
 */
export class SinkRouter {
  private main: ChunkSink | null = null
  private sideSink: ChunkSink | null = null

  setMain(sink: ChunkSink | null): void {
    this.main = sink
  }

  setSide(sink: ChunkSink | null): void {
    this.sideSink = sink
  }

  push(chunk: Int16Array): void {
    if (this.main) this.main(chunk)
    else this.sideSink?.(chunk)
  }

  clear(): void {
    this.main = null
    this.sideSink = null
  }
}
