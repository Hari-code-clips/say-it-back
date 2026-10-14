import { rms } from './endpoint.ts'
import { MIC_RATE } from './wav.ts'

export type MicErrorCode = 'denied' | 'no_device' | 'unsupported' | 'failed'

export class MicError extends Error {
  readonly code: MicErrorCode
  constructor(code: MicErrorCode, message: string) {
    super(message)
    this.name = 'MicError'
    this.code = code
  }
}

export type ChunkSink = (chunk: Int16Array) => void

const WORKLET_URL = `${import.meta.env.BASE_URL}pcm-capture.js`

function toMicError(e: unknown): MicError {
  const name = e instanceof DOMException ? e.name : ''
  if (name === 'NotAllowedError' || name === 'SecurityError') return new MicError('denied', 'Microphone permission was denied.')
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return new MicError('no_device', 'No microphone was found.')
  return new MicError('failed', e instanceof Error ? e.message : 'The microphone could not start.')
}

/**
 * Microphone as a stream of 16 kHz mono Int16 chunks of 20 ms (640 bytes), via an AudioWorklet.
 * It runs from open() to close(); chunks only reach a consumer through setSink(), which is how
 * the Live driver guarantees that audio leaves the device only inside an answer window.
 * open() must be called from a user gesture (the AudioContext is created before the permission prompt).
 */
export class Mic {
  readonly ctx: AudioContext
  private readonly stream: MediaStream
  private readonly source: MediaStreamAudioSourceNode
  private readonly node: AudioWorkletNode
  private sink: ChunkSink | null = null
  private smoothed = 0
  private closed = false

  private constructor(ctx: AudioContext, stream: MediaStream, source: MediaStreamAudioSourceNode, node: AudioWorkletNode) {
    this.ctx = ctx
    this.stream = stream
    this.source = source
    this.node = node
    node.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
      const chunk = new Int16Array(e.data)
      this.smoothed = Math.max(rms(chunk), this.smoothed * 0.88)
      this.sink?.(chunk)
    }
  }

  static async open(): Promise<Mic> {
    if (!navigator.mediaDevices?.getUserMedia || typeof AudioWorkletNode === 'undefined') {
      throw new MicError('unsupported', 'This browser cannot capture microphone audio.')
    }
    const ctx = new AudioContext({ latencyHint: 'interactive' })
    void ctx.resume().catch(() => undefined)
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      })
    } catch (e) {
      void ctx.close()
      throw toMicError(e)
    }
    try {
      await ctx.audioWorklet.addModule(WORKLET_URL)
      const source = ctx.createMediaStreamSource(stream)
      const node = new AudioWorkletNode(ctx, 'pcm-capture', { processorOptions: { targetRate: MIC_RATE } })
      const mute = ctx.createGain() // the worklet must reach a destination to be pulled
      mute.gain.value = 0
      source.connect(node).connect(mute).connect(ctx.destination)
      return new Mic(ctx, stream, source, node)
    } catch (e) {
      stream.getTracks().forEach((t) => t.stop())
      void ctx.close()
      throw new MicError('failed', e instanceof Error ? e.message : 'The microphone could not start.')
    }
  }

  /** Route chunks to one consumer (or null to drop them). */
  setSink(sink: ChunkSink | null): void {
    this.sink = sink
  }

  /** Smoothed input level, 0..1, for the listening orb. */
  get level(): number {
    return Math.min(1, this.smoothed * 5)
  }

  async close(): Promise<void> {
    if (this.closed) return
    this.closed = true
    this.sink = null
    this.node.port.onmessage = null
    this.source.disconnect()
    this.node.disconnect()
    this.stream.getTracks().forEach((t) => t.stop())
    await this.ctx.close().catch(() => undefined)
  }
}
