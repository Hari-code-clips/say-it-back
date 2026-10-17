// Types shared by the two ways of running a briefing round: Live (WebSocket relay) and Turn (TTS).
import type { AnswerClip } from '../audio/capture.ts'
import type { ClipSource } from '../audio/clipSource.ts'

export type SegmentKind = 'instruction' | 'question' | 'thanks' | 'closing'

/** What the worker screen shows. Both modes emit the same phases. */
export type StagePhase =
  | { kind: 'connecting' }
  | { kind: 'speaking'; segment: SegmentKind; qid?: string }
  | { kind: 'listening'; qid: string }
  | { kind: 'finishing' }

export interface StageEvents {
  onPhase(phase: StagePhase): void
  /** `text` is the whole current line for that role. The model's line grows as its words are heard (see CaptionPacer), not as they arrive. */
  onCaption(role: 'model' | 'worker', text: string, final: boolean): void
  /** Voice activity inside the answer window. */
  onSpeech?(speaking: boolean): void
}

export type SessionErrorCode =
  | 'connect_failed'
  | 'socket_closed'
  | 'timeout'
  | 'protocol'
  | 'aborted'
  | 'bad_ticket'
  | 'bad_message'
  | 'invalid_state'
  | 'limit'
  | 'upstream_busy'
  | 'tts_failed'
  | 'unknown'

export class SessionError extends Error {
  readonly code: SessionErrorCode
  /** The relay's own code, when the failure came from an `error` frame. */
  readonly serverCode?: string
  /** `options.cause`: the error underneath, e.g. the ApiError that made a TTS call fail. */
  constructor(code: SessionErrorCode, message: string, serverCode?: string, options?: ErrorOptions) {
    super(message, options)
    this.name = 'SessionError'
    this.code = code
    this.serverCode = serverCode
  }
}

export interface SessionResult {
  /** One answer clip per question id, in the order asked. */
  clips: Record<string, AnswerClip>
  /** v0.4: question ids answered with a stored sample answer (sent as `meta.sampleAnswers`). */
  sampleAnswers: string[]
  model?: string
  turnTaking?: 'manual' | 'auto'
}

export interface BriefingSession {
  run(): Promise<SessionResult>
  /** The "Done" tap: end the open answer window now. */
  finishAnswer(): void
  /**
   * "Use the sample answer": play a stored clip into the open answer window instead of the mic. False when none is open, or
   * when the open window is not `qid`'s (the question it was tapped for).
   */
  useSample(source: ClipSource, qid: string): boolean
  /** Supervisor ends the briefing. */
  abort(): void
}

export const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))
