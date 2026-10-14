// 24 kHz playback queue: Live model audio (PCM16 LE) and turn-mode WAVs play back to back;
// flush() drops everything on `interrupted`. Adapted from the verified stack probe.

export const PLAY_RATE = 24_000

/** A queued buffer starts this far (seconds) after the clock, so it is never scheduled in the past. */
const START_LEAD = 0.02

export class Player {
  private ctx: AudioContext | null = null
  private out: GainNode | null = null
  private analyser: AnalyserNode | null = null
  private samples: Float32Array<ArrayBuffer> | null = null
  private nextTime = 0
  private readonly sources = new Set<AudioBufferSourceNode>()
  private idleWaiters: Array<() => void> = []
  private carry: number | null = null // a dangling odd byte between binary frames

  /** Create and resume the context. Call from a user gesture. */
  async start(): Promise<void> {
    if (!this.ctx) {
      const ctx = new AudioContext({ sampleRate: PLAY_RATE, latencyHint: 'interactive' })
      const out = ctx.createGain()
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 1024
      out.connect(analyser)
      analyser.connect(ctx.destination)
      this.ctx = ctx
      this.out = out
      this.analyser = analyser
      this.samples = new Float32Array(analyser.fftSize)
    }
    if (this.ctx.state === 'suspended') await this.ctx.resume()
  }

  /** Queue raw PCM16 little-endian mono at 24 kHz (a binary frame from the Live relay). */
  enqueue(frame: ArrayBuffer): void {
    let bytes = new Uint8Array(frame)
    if (this.carry !== null) {
      const joined = new Uint8Array(bytes.length + 1)
      joined[0] = this.carry
      joined.set(bytes, 1)
      bytes = joined
      this.carry = null
    }
    if (bytes.length % 2 === 1) {
      this.carry = bytes[bytes.length - 1] ?? 0
      bytes = bytes.subarray(0, bytes.length - 1)
    }
    if (bytes.length === 0 || !this.ctx) return
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
    const f32 = new Float32Array(bytes.length / 2)
    for (let i = 0; i < f32.length; i++) f32[i] = view.getInt16(i * 2, true) / 32768
    const buffer = this.ctx.createBuffer(1, f32.length, PLAY_RATE)
    buffer.copyToChannel(f32, 0)
    this.schedule(buffer)
  }

  /**
   * Decode and play a WAV (turn-mode TTS). Resolves when it has finished playing. `onStart` is called once the clip is
   * queued, with the AudioContext time (seconds) it starts at and its length, so a caption can follow the voice.
   */
  async playWav(wav: Blob | ArrayBuffer, onStart?: (start: number, seconds: number) => void): Promise<void> {
    if (!this.ctx) throw new Error('Player not started')
    const data = wav instanceof Blob ? await wav.arrayBuffer() : wav
    const buffer = await this.ctx.decodeAudioData(data.slice(0))
    const start = this.schedule(buffer)
    onStart?.(start, buffer.duration)
    await this.whenIdle()
  }

  /** The AudioContext clock (seconds): what the worker has heard is what this clock has played. 0 before `start()`. */
  get currentTime(): number {
    return this.ctx?.currentTime ?? 0
  }

  /** AudioContext time at which audio queued now would start playing: the end of the queue, or just ahead of the clock when it is empty. */
  get nextStart(): number {
    return Math.max(this.currentTime + START_LEAD, this.nextTime)
  }

  private schedule(buffer: AudioBuffer): number {
    const ctx = this.ctx
    const out = this.out
    const at = this.nextStart
    if (!ctx || !out) return at
    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.connect(out)
    source.start(at)
    this.nextTime = at + buffer.duration
    this.sources.add(source)
    source.onended = () => {
      this.sources.delete(source)
      if (this.sources.size === 0) this.releaseIdle()
    }
    return at
  }

  /** Stop everything now (barge-in): the contract's `interrupted`. */
  flush(): void {
    for (const s of this.sources) {
      s.onended = null
      try {
        s.stop()
      } catch {
        /* already stopped */
      }
    }
    this.sources.clear()
    this.nextTime = 0
    this.carry = null
    this.releaseIdle()
  }

  /** Resolves when nothing is scheduled any more (or after the timeout). */
  whenIdle(timeoutMs = 120_000): Promise<void> {
    if (this.sources.size === 0) return Promise.resolve()
    return new Promise((resolve) => {
      const done = () => {
        clearTimeout(timer)
        resolve()
      }
      const timer = setTimeout(done, timeoutMs)
      this.idleWaiters.push(done)
    })
  }

  private releaseIdle(): void {
    const waiters = this.idleWaiters
    this.idleWaiters = []
    for (const w of waiters) w()
  }

  get busy(): boolean {
    return this.sources.size > 0
  }

  /** Smoothed output level, 0..1, for the speaking orb. */
  get level(): number {
    if (!this.analyser || !this.samples || !this.busy) return 0
    this.analyser.getFloatTimeDomainData(this.samples)
    let sum = 0
    for (const v of this.samples) sum += v * v
    return Math.min(1, Math.sqrt(sum / this.samples.length) * 4)
  }

  async close(): Promise<void> {
    this.flush()
    const ctx = this.ctx
    this.ctx = null
    await ctx?.close().catch(() => undefined)
  }
}
