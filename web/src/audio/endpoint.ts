// Energy-based end-of-answer detection on 20 ms PCM16 frames (no model, no network).
// Rule: after speech has started, ~1.5 s of silence ends the answer; a hard cap ends it at 30 s.
// (A "Done" tap is handled by the caller.) The noise floor is the quietest frame of the last
// two seconds, so steady site noise raises the bar instead of keeping the window open.

export type EndReason = 'silence' | 'max' | 'done' | 'abort'

export interface EndpointConfig {
  frameMs: number
  /** Silence after speech that ends the answer. */
  silenceMs: number
  /** Hard cap for one answer window. */
  maxMs: number
  /** A voiced run this long counts as speech (ignores clicks and thumps). */
  minSpeechMs: number
  /** A voiced blip this long inside the silence resets the silence timer. */
  blipMs: number
  /** RMS floor (0..1) below which a frame is never speech: about -38 dBFS. */
  absThreshold: number
  /** Speech must beat the running noise floor by this factor. */
  snrFactor: number
  /** Ceiling for the adaptive threshold, so long loud speech can never read as silence. */
  maxThreshold: number
  /** Frames of history for the noise-floor minimum (100 x 20 ms = 2 s). */
  noiseWindowFrames: number
}

export const DEFAULT_ENDPOINT: EndpointConfig = {
  frameMs: 20,
  silenceMs: 1500,
  maxMs: 30_000,
  minSpeechMs: 120,
  blipMs: 60,
  absThreshold: 0.012,
  snrFactor: 3,
  maxThreshold: 0.06,
  noiseWindowFrames: 100,
}

/** RMS of an Int16 frame, normalised to 0..1. */
export function rms(pcm: Int16Array): number {
  if (pcm.length === 0) return 0
  let sum = 0
  for (let i = 0; i < pcm.length; i++) {
    const v = (pcm[i] ?? 0) / 32768
    sum += v * v
  }
  return Math.sqrt(sum / pcm.length)
}

export class EndpointDetector {
  private readonly cfg: EndpointConfig
  private readonly recent: number[] = []
  private voicedRunMs = 0
  private silenceRunMs = 0
  private elapsed = 0
  private speech = 0
  private started = false

  constructor(cfg: Partial<EndpointConfig> = {}) {
    this.cfg = { ...DEFAULT_ENDPOINT, ...cfg }
  }

  /** Feed one frame; returns the reason when the window should end, else null. */
  push(frame: Int16Array): 'silence' | 'max' | null {
    const { frameMs } = this.cfg
    const level = rms(frame)
    this.recent.push(level)
    if (this.recent.length > this.cfg.noiseWindowFrames) this.recent.shift()
    const noise = Math.min(...this.recent)
    const threshold = Math.min(Math.max(this.cfg.absThreshold, noise * this.cfg.snrFactor), this.cfg.maxThreshold)
    const voiced = level > threshold

    this.elapsed += frameMs
    if (voiced) {
      this.voicedRunMs += frameMs
      this.speech += frameMs
      if (this.voicedRunMs >= this.cfg.minSpeechMs) this.started = true
      if (this.started && this.voicedRunMs >= this.cfg.blipMs) this.silenceRunMs = 0
    } else {
      this.voicedRunMs = 0
      if (this.started) this.silenceRunMs += frameMs
    }

    if (this.started && this.silenceRunMs >= this.cfg.silenceMs) return 'silence'
    if (this.elapsed >= this.cfg.maxMs) return 'max'
    return null
  }

  /** True once real speech (not just noise) has been heard in this window. */
  get heardSpeech(): boolean {
    return this.started
  }
  /** True while the latest frames are voiced. */
  get speaking(): boolean {
    return this.voicedRunMs > 0
  }
  get speechMs(): number {
    return this.speech
  }
  get elapsedMs(): number {
    return this.elapsed
  }
}
