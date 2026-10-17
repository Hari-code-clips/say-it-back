// One answer window, shared by the Live and Turn sessions. It records from the mic, unless the supervisor taps
// "Use the sample answer" (endpoint 24): then the mic's part is dropped and the stored clip is played into the same window
// instead. In Live mode that clip is what goes to the socket; in both modes it is the question's WAV for POST /check.
import { captureAnswer, type AnswerClip, type CaptureHandle, type CaptureOptions } from '../audio/capture.ts'
import type { ClipSource } from '../audio/clipSource.ts'
import type { ChunkSource } from '../audio/source.ts'

/**
 * A stored clip's pauses must not end the window: it ends when the clip has been played (ClipSource.done), on a Done tap,
 * or at the 30 s cap.
 */
const SAMPLE_SILENCE_MS = 30_000

export class AnswerWindow {
  private capture: CaptureHandle | null = null
  private next: ClipSource | null = null
  private openQid: string | null = null
  private readonly sampled: string[] = []

  /** Question ids whose answer was a stored sample, in the order asked. */
  get sampleAnswers(): string[] {
    return [...this.sampled]
  }

  /** The window of `qid`, from `mic` (or a sample, see useSample). `race` lets the session fail the wait. */
  async run(qid: string, mic: ChunkSource, opts: CaptureOptions, race: (p: Promise<AnswerClip>) => Promise<AnswerClip>): Promise<AnswerClip> {
    this.openQid = qid
    try {
      let clip = await race(this.start(mic, opts))
      while (this.next) {
        const source = this.next
        this.next = null
        if (!this.sampled.includes(qid)) this.sampled.push(qid)
        clip = await race(this.start(source, { ...opts, config: { ...opts.config, silenceMs: SAMPLE_SILENCE_MS } }, source.done))
      }
      return clip
    } finally {
      this.capture?.finish('abort') // no-op when it already ended; guarantees the sink is released
      this.capture = null
      this.openQid = null
    }
  }

  /** The window that is open now, if any. */
  get open(): string | null {
    return this.openQid
  }

  /** "Done" (or abort): end the open window now. */
  finish(reason: 'done' | 'abort'): void {
    this.capture?.finish(reason)
  }

  /**
   * Answer the open window with a stored clip instead of the mic. The mic's chunks so far are dropped (the WAV is the
   * clip alone) and the clip is played into the same window. False when no window is open, or (v0.4 review) when the open
   * window is not the question the sample was tapped for.
   */
  useSample(source: ClipSource, qid?: string): boolean {
    if (!this.capture || !this.openQid) return false
    if (qid !== undefined && qid !== this.openQid) return false
    this.next = source
    this.capture.finish('abort')
    return true
  }

  private start(source: ChunkSource, opts: CaptureOptions, until?: Promise<void>): Promise<AnswerClip> {
    const capture = captureAnswer(source, opts)
    this.capture = capture
    void until?.then(() => capture.finish('done'))
    return capture.done
  }
}
