// Turn mode (fallback): each segment is spoken from POST /api/tts audio (lines of the round's own script), and each answer is
// recorded locally exactly like Live (same mic, same end-of-answer rule, same WAV for /check). A stored sample answer
// (endpoint 24) can replace the mic in a window, and is then the recorded WAV.
import type { AnswerClip } from '../audio/capture.ts'
import type { ClipSource } from '../audio/clipSource.ts'
import type { Mic } from '../audio/mic.ts'
import type { Player } from '../audio/player.ts'
import { chunkForTts, revealPlan, type RevealStep } from '../lib/sentences.ts'
import { AnswerWindow } from './answerWindow.ts'
import { CaptionPacer, playerClock, type PacerClock } from './captionPacer.ts'
import { SessionError, sleep, type BriefingSession, type SessionResult, type StageEvents, type StagePhase } from './session.ts'

export interface TurnSessionInit {
  instruction: string
  questions: { id: string; text: string }[]
  closing: string
  mic: Mic
  player: Player
  events: StageEvents
  /** POST /api/tts for a line of this round's script (max 600 chars per call; longer segments are chunked into slices of themselves). */
  tts: (text: string) => Promise<Blob>
  /** The clock the captions are paced on (see CaptionPacer): the player's AudioContext clock unless a test drives its own. */
  clock?: PacerClock
}

export class TurnSession implements BriefingSession {
  private readonly init: TurnSessionInit
  private readonly pacer: CaptionPacer
  private readonly window = new AnswerWindow()
  private aborted = false

  constructor(init: TurnSessionInit) {
    this.init = init
    this.pacer = new CaptionPacer(init.clock ?? playerClock(init.player), (text, final) => init.events.onCaption('model', text, final))
  }

  async run(): Promise<SessionResult> {
    const { events, questions, instruction, closing } = this.init
    const clips: Record<string, AnswerClip> = {}
    try {
      events.onPhase({ kind: 'connecting' })
      // Fetch every segment's audio at once; playback starts as soon as the first one is ready.
      const audio = new Map<string, Promise<Blob[]>>()
      const prefetch = (key: string, text: string) => {
        const p = Promise.all(chunkForTts(text).map((t) => this.init.tts(t)))
        p.catch(() => undefined)
        audio.set(key, p)
      }
      prefetch('instruction', instruction)
      for (const q of questions) prefetch(q.id, q.text)
      prefetch('closing', closing)

      await this.speak(audio, 'instruction', instruction, { kind: 'speaking', segment: 'instruction' })
      for (const q of questions) {
        await this.speak(audio, q.id, q.text, { kind: 'speaking', segment: 'question', qid: q.id })
        clips[q.id] = await this.listen(q.id)
      }
      await this.speak(audio, 'closing', closing, { kind: 'speaking', segment: 'closing' })
      events.onPhase({ kind: 'finishing' })
      return { clips, sampleAnswers: this.window.sampleAnswers }
    } catch (e) {
      this.init.player.flush()
      if (e instanceof SessionError) throw e
      // The original error stays as `cause`: a 429 daily_limit from /api/tts must not read as "voice could not be prepared".
      throw new SessionError('tts_failed', e instanceof Error ? e.message : 'The voice could not be prepared.', undefined, { cause: e })
    } finally {
      this.pacer.drop()
      this.window.finish('abort')
      this.init.mic.setSink(null)
    }
  }

  finishAnswer(): void {
    this.window.finish('done')
  }

  useSample(source: ClipSource, qid: string): boolean {
    return this.window.useSample(source, qid)
  }

  abort(): void {
    this.aborted = true
    this.pacer.drop()
    this.window.finish('abort')
    this.init.player.flush()
  }

  private checkAbort(): void {
    if (this.aborted) throw new SessionError('aborted', 'The briefing was ended.')
  }

  private async speak(audio: Map<string, Promise<Blob[]>>, key: string, text: string, phase: StagePhase): Promise<void> {
    const { events, player } = this.init
    this.checkAbort()
    events.onPhase(phase)
    // TTS has no transcription, so the caption is the script, a sentence at a time across each clip (see revealPlan).
    // The first sentence is on screen at once, as a one-sentence question or closing is whole.
    const plan = revealPlan(text, chunkForTts(text).map((chunk) => chunk.length))
    const first = plan[0]?.[0]
    events.onCaption('model', first?.text ?? text, first?.final ?? true)
    const blobs = await audio.get(key)
    this.checkAbort()
    for (const [i, blob] of (blobs ?? []).entries()) {
      await player.playWav(blob, (start, seconds) => this.reveal(i === 0 ? plan[i]?.slice(1) : plan[i], start, seconds))
      this.checkAbort()
    }
    this.pacer.flush() // the whole segment is on screen when its last clip ends
    await sleep(250)
  }

  /** Queue the caption steps of one clip that starts at `start` (AudioContext seconds) and lasts `seconds`. */
  private reveal(steps: RevealStep[] | undefined, start: number, seconds: number): void {
    for (const step of steps ?? []) this.pacer.add(start + step.frac * seconds, step.text, step.final)
  }

  private async listen(qid: string): Promise<AnswerClip> {
    const { events, mic } = this.init
    this.checkAbort()
    events.onCaption('worker', '', true)
    events.onPhase({ kind: 'listening', qid })
    const clip = await this.window.run(qid, mic, { onSpeech: (s) => events.onSpeech?.(s) }, (done) => done)
    this.checkAbort()
    return clip
  }
}
