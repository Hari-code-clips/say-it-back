import { readWavInfo } from '../../src/audio/wav.ts'
import type { FakeClock } from './fakeClock.ts'

/**
 * A stand-in for the browser's AudioContext on a FakeClock, so the real Player (its queue, its start times, its idle
 * notice) runs in a test. A buffer's `onended` fires on the clock when it has played. Returns the undo.
 */
export function installFakeAudio(clock: FakeClock): () => void {
  const saved = (globalThis as { AudioContext?: unknown }).AudioContext

  class Source {
    buffer: { duration: number } | null = null
    onended: (() => void) | null = null
    private cancel: (() => void) | null = null
    connect = (): void => undefined
    start(at: number): void {
      const end = at + (this.buffer?.duration ?? 0)
      this.cancel = clock.later((end - clock.time) * 1000, () => this.onended?.())
    }
    stop(): void {
      this.cancel?.()
    }
  }

  class Context {
    state = 'running'
    destination = {}
    get currentTime(): number {
      return clock.time
    }
    createGain = () => ({ connect: () => undefined })
    createAnalyser = () => ({ fftSize: 0, connect: () => undefined })
    createBuffer = (_channels: number, length: number, rate: number) => ({ duration: length / rate, copyToChannel: () => undefined })
    createBufferSource = () => new Source()
    decodeAudioData = async (wav: ArrayBuffer) => ({ duration: (readWavInfo(new Uint8Array(wav))?.durationMs ?? 0) / 1000 })
    resume = async () => undefined
    close = async () => undefined
  }

  ;(globalThis as { AudioContext?: unknown }).AudioContext = Context
  return () => {
    ;(globalThis as { AudioContext?: unknown }).AudioContext = saved
  }
}
