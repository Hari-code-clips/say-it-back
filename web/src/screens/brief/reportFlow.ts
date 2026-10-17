// The worker's "Report a problem" (endpoint 21) as a plain state machine, so its rules are tested without a DOM:
//   closed -> choose -> (opening -> recording ->) sending -> sent -> closed
//   sending -> failed -> (retry, with the same recording) sending
//   failed -> confirm_discard -> closed (deliberately deleted) | failed (kept)
// A report that is on its way, or failed and not deliberately deleted, holds the worker screen: the page must not move on
// (the result screen, the script) and lose it (v0.4 review).
import { captureAnswer, type CaptureHandle, type CaptureOptions } from '../../audio/capture.ts'
import type { ChunkSource } from '../../audio/source.ts'

export type ReportState =
  | { kind: 'closed' }
  | { kind: 'choose' }
  | { kind: 'opening' }
  | { kind: 'recording'; startedAt: number }
  | { kind: 'sending' }
  | { kind: 'sent' }
  | { kind: 'failed'; audio: Blob | null }
  | { kind: 'confirm_discard'; audio: Blob | null }
  | { kind: 'no_mic' }

export interface ReportSource {
  source: ChunkSource
  /** Close what was opened for the report (nothing, when it borrowed the briefing's mic). */
  release: () => Promise<void>
}

export interface ReportDeps {
  /** The run's mic when the briefing is running, else one opened for the report. Called from the tap. */
  openSource: () => Promise<ReportSource>
  /** POST endpoint 21: with the WAV, or with none for a tap. */
  send: (audio: Blob | null) => Promise<void>
  onChange: (state: ReportState) => void
  /** The capture of an answer window, by default; a test can hand in its own. */
  capture?: (source: ChunkSource, opts: CaptureOptions) => CaptureHandle
  now?: () => number
  /** How long the confirmation stays before the button comes back. */
  sentMs?: number
}

/** A report's voice is at most 30 s (the contract's limit); 3 s of quiet after speech sends it, as a finished answer does. */
const REPORT_CAPTURE = { maxMs: 30_000, silenceMs: 3000 }
/** Below this much speech the recording holds no words: it is sent as a tap, which costs no Gemini call. */
const MIN_SPEECH_MS = 300

/** Recording, sending, or failed and not deliberately deleted: the worker screen must stay. */
export const holdsPage = (s: ReportState): boolean =>
  s.kind === 'opening' || s.kind === 'recording' || s.kind === 'sending' || s.kind === 'failed' || s.kind === 'confirm_discard'

export class ReportFlow {
  private current: ReportState = { kind: 'closed' }
  private readonly deps: ReportDeps
  private handle: CaptureHandle | null = null
  private held: ReportSource | null = null
  private sentTimer: ReturnType<typeof setTimeout> | undefined
  private disposed = false

  constructor(deps: ReportDeps) {
    this.deps = deps
  }

  get state(): ReportState {
    return this.current
  }

  get holds(): boolean {
    return holdsPage(this.current)
  }

  /** The recording's level, 0..1, for the meter. */
  get level(): number {
    return this.held?.source.level ?? 0
  }

  open(): void {
    if (this.current.kind === 'closed' || this.current.kind === 'sent') this.set({ kind: 'choose' })
  }

  async speak(): Promise<void> {
    if (this.current.kind !== 'choose') return
    this.set({ kind: 'opening' })
    let src: ReportSource
    try {
      src = await this.deps.openSource()
    } catch {
      this.set({ kind: 'no_mic' })
      return
    }
    if (this.disposed) return void src.release()
    this.held = src
    const handle = (this.deps.capture ?? captureAnswer)(src.source, { config: REPORT_CAPTURE })
    this.handle = handle
    this.set({ kind: 'recording', startedAt: (this.deps.now ?? Date.now)() })
    const clip = await handle.done
    this.handle = null
    this.held = null
    await src.release().catch(() => undefined)
    if (clip.reason === 'abort') return void this.set({ kind: 'closed' })
    await this.deliver(clip.speechMs >= MIN_SPEECH_MS ? clip.wav : null)
  }

  /** A report with no words. */
  tap(): Promise<void> {
    if (this.current.kind !== 'choose' && this.current.kind !== 'no_mic') return Promise.resolve()
    return this.deliver(null)
  }

  /** Send what has been recorded so far. */
  finish(): void {
    this.handle?.finish('done')
  }

  /** Send a failed report again: the same recording, never a new one. */
  retry(): Promise<void> {
    if (this.current.kind !== 'failed') return Promise.resolve()
    return this.deliver(this.current.audio)
  }

  /**
   * Cancel what is under way. A recording is dropped (nothing was sent yet). A failed report is not dropped here: it asks to
   * confirm first (`confirmDiscard`), so a report is only ever lost on purpose.
   */
  cancel(): void {
    if (this.handle) return this.handle.finish('abort')
    if (this.current.kind === 'failed') return this.set({ kind: 'confirm_discard', audio: this.current.audio })
    if (this.current.kind === 'choose' || this.current.kind === 'no_mic') this.set({ kind: 'closed' })
  }

  /** "Delete this report?" -> yes. */
  confirmDiscard(): void {
    if (this.current.kind === 'confirm_discard') this.set({ kind: 'closed' })
  }

  /** "Delete this report?" -> keep it. */
  keep(): void {
    if (this.current.kind === 'confirm_discard') this.set({ kind: 'failed', audio: this.current.audio })
  }

  /** Mounted (again): React's StrictMode runs an effect's cleanup once in development before the real mount. */
  revive(): void {
    this.disposed = false
  }

  dispose(): void {
    this.disposed = true
    clearTimeout(this.sentTimer)
    this.handle?.finish('abort')
    void this.held?.release()
  }

  private async deliver(audio: Blob | null): Promise<void> {
    this.set({ kind: 'sending' })
    try {
      await this.deps.send(audio)
      if (this.disposed) return
      this.set({ kind: 'sent' })
      clearTimeout(this.sentTimer)
      this.sentTimer = setTimeout(() => {
        if (!this.disposed && this.current.kind === 'sent') this.set({ kind: 'closed' })
      }, this.deps.sentMs ?? 4000)
    } catch {
      if (!this.disposed) this.set({ kind: 'failed', audio })
    }
  }

  private set(next: ReportState): void {
    this.current = next
    this.deps.onChange(next)
  }
}
