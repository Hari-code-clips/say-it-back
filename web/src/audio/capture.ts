import { EndpointDetector, type EndReason, type EndpointConfig } from './endpoint.ts'
import type { Mic } from './mic.ts'
import { concatInt16, encodeWav } from './wav.ts'

export interface AnswerClip {
  /** 16 kHz mono WAV of the whole answer window: the same PCM that was streamed to Live. */
  wav: Blob
  pcmBytes: number
  reason: EndReason
  speechMs: number
  durationMs: number
}

export interface CaptureOptions {
  /** Called with every chunk, in order, before the end-of-answer check (the Live socket send). */
  forward?: (chunk: Int16Array) => void
  /** Voice activity for the UI. */
  onSpeech?: (speaking: boolean) => void
  config?: Partial<EndpointConfig>
}

export interface CaptureHandle {
  done: Promise<AnswerClip>
  /** End the window now ("Done" tap, supervisor abort). No-op after it has ended. */
  finish(reason?: 'done' | 'abort'): void
}

/**
 * One answer window: takes the mic, records every chunk, forwards the same chunk, and ends on
 * ~1.5 s of silence after speech, on finish() (Done tap), or at the 30 s cap. On end the mic sink
 * is released synchronously, so nothing is forwarded after the window closes.
 */
export function captureAnswer(mic: Mic, opts: CaptureOptions = {}): CaptureHandle {
  const detector = new EndpointDetector(opts.config)
  const chunks: Int16Array[] = []
  let ended = false
  let lastSpeaking = false
  let resolveClip!: (clip: AnswerClip) => void
  const done = new Promise<AnswerClip>((resolve) => {
    resolveClip = resolve
  })

  const end = (reason: EndReason) => {
    if (ended) return
    ended = true
    mic.setSink(null)
    const pcm = concatInt16(chunks)
    resolveClip({
      wav: encodeWav(pcm),
      pcmBytes: pcm.byteLength,
      reason,
      speechMs: detector.speechMs,
      durationMs: detector.elapsedMs,
    })
  }

  mic.setSink((chunk) => {
    if (ended) return
    chunks.push(chunk)
    opts.forward?.(chunk)
    const reason = detector.push(chunk)
    if (detector.speaking !== lastSpeaking) {
      lastSpeaking = detector.speaking
      opts.onSpeech?.(lastSpeaking)
    }
    if (reason) end(reason)
  })

  return { done, finish: (reason = 'done') => end(reason) }
}
