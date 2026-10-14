// The browser side of endpoint 20: drives one Live briefing round over the relay WebSocket.
//
//   start{ticket} -> ready
//   READ_INSTRUCTION -> turn_complete
//   per question: ASK qid -> turn_complete -> answer_start -> mic chunks -> answer_end -> turn_complete
//                 (the last one is the neutral thanks: waited for, but not required)
//   CLOSE -> turn_complete -> stop
//
// Mic audio leaves the device only between answer_start and answer_end: the mic sink is attached
// after answer_start is sent and released before answer_end is sent. The same chunks are kept as
// the question's WAV for POST /check. The browser never talks to Gemini; it only sends cues and audio.
import { captureAnswer, type AnswerClip, type CaptureHandle } from '../audio/capture.ts'
import type { Mic } from '../audio/mic.ts'
import type { Player } from '../audio/player.ts'
import { CaptionPacer, playerClock, type PacerClock } from './captionPacer.ts'
import { CaptionMerger } from './captions.ts'
import { resolveWsUrl } from './liveUrl.ts'
import { MAX_BINARY_FRAME, parseServerMessage, type ClientMessage, type Cue, type ServerMessage } from './protocol.ts'
import { SessionError, sleep, type BriefingSession, type SessionErrorCode, type SessionResult, type StageEvents, type StagePhase } from './session.ts'
import { OPEN, type LiveSocket, type SocketFactory } from './socket.ts'

export interface LiveSessionInit {
  /** `wsUrl` from endpoint 11, used as given. */
  wsUrl: string
  /** Single-use ticket from endpoint 11. Sent once in `start`; never logged. */
  ticket: string
  questionIds: string[]
  mic: Mic
  player: Player
  events: StageEvents
  openSocket: SocketFactory
  /** Where the page is served, to resolve a same-origin wsUrl. */
  location?: { protocol: string; host: string }
  /** No server frame for this long while waiting = failure, unless queued speech is still playing. Contract idle timeout is 60 s. */
  idleMs?: number
  /**
   * After `stop`, wait this long for the relay to close the socket before returning. The relay writes
   * `round.live` when the socket closes, and POST /check reads it, so /check must not overtake it.
   */
  stopWaitMs?: number
  /** How long to wait for the model's neutral thanks after an answer before going on without it. */
  thanksWaitMs?: number
  /** The clock the model's captions are paced on (see CaptionPacer): the player's AudioContext clock unless a test drives its own. */
  clock?: PacerClock
  /** Frame-level trace for tests (message types and sizes only, never the ticket). */
  trace?: (line: string) => void
}

/** Default for `stopWaitMs`: long enough for a Firestore write, short enough not to stall the check. */
const STOP_WAIT_MS = 3000

/** Default for `thanksWaitMs`. The thanks is a courtesy: a model that says nothing must not fail the round. */
const THANKS_WAIT_MS = 12_000

const SERVER_CODES: Record<string, SessionErrorCode> = {
  bad_ticket: 'bad_ticket',
  bad_message: 'bad_message',
  invalid_state: 'invalid_state',
  limit: 'limit',
  upstream_busy: 'upstream_busy',
}

/** Frame label for traces. The ticket is never included. */
function describe(msg: ClientMessage): string {
  switch (msg.type) {
    case 'start':
      return 'start'
    case 'cue':
      return msg.cue === 'ASK' ? `cue ASK ${msg.qid}` : `cue ${msg.cue}`
    case 'answer_start':
    case 'answer_end':
      return `${msg.type} ${msg.qid}`
    case 'stop':
      return 'stop'
  }
}

interface Deferred<T> {
  promise: Promise<T>
  resolve: (v: T) => void
  reject: (e: unknown) => void
}
function deferred<T>(): Deferred<T> {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

export class LiveSession implements BriefingSession {
  private readonly init: LiveSessionInit
  private readonly captions = new CaptionMerger() // the worker's line; the model's goes through the pacer
  private readonly pacer: CaptionPacer
  private readonly failure = deferred<never>()
  private readonly closed = deferred<void>()
  private ws: LiveSocket | null = null
  private ready = deferred<{ model: string; turnTaking: 'manual' | 'auto' }>()
  private turn: Deferred<void> | null = null
  private capture: CaptureHandle | null = null
  private armIdle: (() => void) | null = null
  private opened = false
  private closing = false
  private failed = false

  constructor(init: LiveSessionInit) {
    this.init = init
    this.pacer = new CaptionPacer(init.clock ?? playerClock(init.player), (text, final) => init.events.onCaption('model', text, final))
    this.failure.promise.catch(() => undefined) // consumed through until(); never an unhandled rejection
  }

  async run(): Promise<SessionResult> {
    const { events, questionIds } = this.init
    const clips: Record<string, AnswerClip> = {}
    try {
      events.onPhase({ kind: 'connecting' })
      const info = await this.connect()
      await this.cue({ cue: 'READ_INSTRUCTION' }, { kind: 'speaking', segment: 'instruction' })
      for (const qid of questionIds) {
        await this.cue({ cue: 'ASK', qid }, { kind: 'speaking', segment: 'question', qid })
        clips[qid] = await this.answerWindow(qid)
      }
      await this.cue({ cue: 'CLOSE' }, { kind: 'speaking', segment: 'closing' })
      events.onPhase({ kind: 'finishing' })
      this.closing = true // from here a close is the expected end, not a failure
      this.send({ type: 'stop' })
      await this.waitForServerClose(this.init.stopWaitMs ?? STOP_WAIT_MS)
      return { clips, model: info.model, turnTaking: info.turnTaking }
    } catch (e) {
      this.init.player.flush()
      throw e instanceof SessionError ? e : new SessionError('unknown', e instanceof Error ? e.message : String(e))
    } finally {
      this.cleanup()
    }
  }

  finishAnswer(): void {
    this.capture?.finish('done')
  }

  abort(): void {
    this.fail(new SessionError('aborted', 'The briefing was ended.'))
    this.cleanup()
  }

  // ---- connection ----

  private connect(): Promise<{ model: string; turnTaking: 'manual' | 'auto' }> {
    const loc = this.init.location ?? window.location
    let ws: LiveSocket
    try {
      ws = this.init.openSocket(resolveWsUrl(this.init.wsUrl, loc))
    } catch {
      throw new SessionError('connect_failed', 'The voice connection could not be opened.')
    }
    this.ws = ws
    ws.binaryType = 'arraybuffer'
    ws.onopen = () => {
      this.opened = true
      this.send({ type: 'start', ticket: this.init.ticket })
    }
    ws.onmessage = (ev) => this.onFrame(ev.data)
    ws.onerror = () => this.fail(new SessionError(this.opened ? 'socket_closed' : 'connect_failed', 'The voice connection failed.'))
    ws.onclose = (ev) => {
      this.closed.resolve()
      this.pacer.drop()
      if (this.closing) return
      const code: SessionErrorCode = ev.code === 4401 ? 'bad_ticket' : this.opened ? 'socket_closed' : 'connect_failed'
      this.fail(new SessionError(code, `The voice connection closed (${ev.code}).`))
    }
    return this.until(this.ready.promise, 'connecting')
  }

  private onFrame(data: unknown): void {
    this.armIdle?.()
    if (typeof data === 'string') {
      const msg = parseServerMessage(data)
      if (msg) this.onServer(msg)
    } else if (data instanceof ArrayBuffer) {
      this.init.trace?.(`<- BIN ${data.byteLength}`)
      this.init.player.enqueue(data)
    }
  }

  private onServer(msg: ServerMessage): void {
    this.init.trace?.(`<- ${msg.type}${msg.type === 'error' ? ` ${msg.code}` : ''}`)
    switch (msg.type) {
      case 'ready':
        this.ready.resolve({ model: msg.model, turnTaking: msg.turnTaking })
        break
      case 'caption':
        // The worker's words show at once. The model's show as the audio that follows them plays (see CaptionPacer):
        // `nextStart` is where the audio queued so far ends, i.e. where in the speech this frame arrived.
        if (msg.role === 'model') this.pacer.frame(msg.text, msg.final, this.init.player.nextStart)
        else this.init.events.onCaption('worker', this.captions.push('worker', msg.text), msg.final)
        break
      case 'turn_complete':
        this.turn?.resolve()
        this.turn = null
        break
      case 'interrupted':
        this.init.player.flush()
        this.pacer.drop() // the speech it was waiting for is gone
        break
      case 'error':
        this.fail(new SessionError(SERVER_CODES[msg.code] ?? 'unknown', msg.message || 'The voice service reported an error.', msg.code))
        break
    }
  }

  // ---- the script ----

  /** Send a cue and wait for the model to finish speaking it (frames in, playback drained). */
  private async cue(cue: Cue, phase: StagePhase): Promise<void> {
    this.pacer.drop()
    this.init.events.onPhase(phase)
    const turn = this.expectTurn()
    this.send({ type: 'cue', ...cue })
    await this.until(turn.promise, phase.kind === 'speaking' ? phase.segment : 'the cue')
    await this.playbackDrained()
    await sleep(250) // a natural beat between segments
  }

  /** Local wait: the queued speech has finished playing, and its caption is complete. Not subject to the relay-idle timeout. */
  private async playbackDrained(): Promise<void> {
    await Promise.race([this.init.player.whenIdle(), this.failure.promise])
    this.pacer.flush()
  }

  private async answerWindow(qid: string): Promise<AnswerClip> {
    const { events, mic } = this.init
    this.captions.reset('worker')
    events.onPhase({ kind: 'listening', qid })
    this.send({ type: 'answer_start', qid })
    const capture = captureAnswer(mic, {
      forward: (chunk) => this.sendAudio(chunk),
      onSpeech: (speaking) => events.onSpeech?.(speaking),
    })
    this.capture = capture
    let clip: AnswerClip
    try {
      clip = await Promise.race([capture.done, this.failure.promise])
    } finally {
      capture.finish('abort') // no-op when it already ended; guarantees the sink is released
      this.capture = null
    }
    // The mic sink is released: no audio can be sent after this line.
    this.pacer.drop() // the thanks is a new utterance
    const thanks = this.expectTurn()
    this.send({ type: 'answer_end', qid })
    events.onPhase({ kind: 'speaking', segment: 'thanks', qid })
    await this.untilOrGiveUp(thanks.promise, this.init.thanksWaitMs ?? THANKS_WAIT_MS)
    await this.playbackDrained()
    return clip
  }

  // ---- plumbing ----

  private expectTurn(): Deferred<void> {
    this.turn = deferred<void>()
    return this.turn
  }

  /**
   * Wait for `p`, failing on socket failure or when the relay goes quiet for idleMs. Quiet does not count while
   * queued speech is still playing: Live sends the audio of a turn well ahead of real time (a 30 s read-out is on
   * the wire within about 8 s) and ends the turn when the speech would end, so the socket is silent for most of
   * a long read-out.
   */
  private async until<T>(p: Promise<T>, what: string): Promise<T> {
    const idleMs = this.init.idleMs ?? 30_000
    let timer: ReturnType<typeof setTimeout> | undefined
    const idle = new Promise<never>((_, reject) => {
      const arm = () => {
        clearTimeout(timer)
        timer = setTimeout(() => {
          if (this.init.player.busy) arm()
          else reject(new SessionError('timeout', `No answer from the voice service while waiting for ${what}.`))
        }, idleMs)
      }
      this.armIdle = arm
      arm()
    })
    idle.catch(() => undefined)
    try {
      return await Promise.race([p, this.failure.promise, idle])
    } finally {
      clearTimeout(timer)
      this.armIdle = null
    }
  }

  /** Wait for `p` at most `maxMs`. Only a failure of the session throws: a reply that never comes just ends the wait. */
  private async untilOrGiveUp(p: Promise<void>, maxMs: number): Promise<void> {
    let timer: ReturnType<typeof setTimeout> | undefined
    const giveUp = new Promise<void>((resolve) => {
      timer = setTimeout(resolve, maxMs)
    })
    try {
      await Promise.race([p, this.failure.promise, giveUp])
    } finally {
      clearTimeout(timer)
    }
  }

  private send(msg: ClientMessage): void {
    const ws = this.ws
    if (!ws || ws.readyState !== OPEN) return
    this.init.trace?.(`-> ${describe(msg)}`)
    ws.send(JSON.stringify(msg))
  }

  private sendAudio(chunk: Int16Array): void {
    const ws = this.ws
    if (!ws || ws.readyState !== OPEN || chunk.byteLength > MAX_BINARY_FRAME) return
    this.init.trace?.(`-> BIN ${chunk.byteLength}`)
    ws.send(chunk as Int16Array<ArrayBuffer>)
  }

  /** Resolves when the relay closes the socket, or after `maxMs`, whichever comes first. */
  private waitForServerClose(maxMs: number): Promise<void> {
    if (!this.ws || this.ws.readyState !== OPEN) return Promise.resolve()
    return new Promise((resolve) => {
      const timer = setTimeout(resolve, maxMs)
      void this.closed.promise.then(() => {
        clearTimeout(timer)
        resolve()
      })
    })
  }

  private fail(err: SessionError): void {
    this.pacer.drop()
    if (this.failed) return
    this.failed = true
    this.failure.reject(err)
  }

  private cleanup(): void {
    this.pacer.drop()
    this.capture?.finish('abort')
    this.capture = null
    this.init.mic.setSink(null)
    const ws = this.ws
    this.closing = true
    if (ws && ws.readyState === OPEN) {
      try {
        ws.close(1000, 'done')
      } catch {
        /* already closing */
      }
    }
  }
}
