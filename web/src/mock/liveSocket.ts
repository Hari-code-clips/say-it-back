import type { Briefing, Round } from '../api/types.ts'
import type { LiveSocket, SocketFactory } from '../live/socket.ts'
import { seedOf, speechPcm, spokenSeconds } from './audio.ts'
import { longAnswer } from './longScripts.ts'
import { LEAD, LEAD_ROUND1_ANSWERS, NEUTRAL_THANKS, isLeadDemo } from './script.ts'
import { getBriefing } from './store.ts'

// A mock of the Live relay (endpoint 20) that speaks the real protocol: ready, cue -> audio +
// captions + turn_complete, answer windows with mic bytes, neutral thanks, stop. The audio is
// synthetic (see ./audio.ts) and paced like the real model (see BURST). No model runs.

const RATE = 24_000
const FRAME_MS = 100 // 2,400 samples = 4,800 bytes per frame, under the 8 KB limit
/**
 * The real model sends a turn's audio and captions about 4x faster than real time, then nothing until
 * turn_complete, which comes when the speech would end (findings.md, 2026-10-13 16:58). A fake that streamed
 * in real time hid two idle-watchdog bugs, so this one bursts too: the caption is complete early, the speech
 * plays on, and turn_complete arrives at the end.
 */
const BURST = 4
/**
 * The real relay's captions run ahead of the audio they transcribe: the first one arrives with 0.15 s of audio and holds
 * about a second of words, and a turn's text is complete well before its audio ends (ws-frames.jsonl of the 83 s
 * integration run: 81 captions, about 1 s of speech each). So the caption for each second of speech goes out with the
 * first audio frame of that second, and the final caption with the last frame of the burst.
 */
const CAPTION_FRAMES = 1000 / FRAME_MS
const MIN_ANSWER_BYTES = 16_000 * 2 * 0.8

/** The pieces the transcription arrives in: words, or single characters in scripts written without spaces. */
const pieces = (text: string): string[] => text.match(/[\u3400-\u9fff]|[^\u3400-\u9fff\s]+|\s+/g) ?? [text]

export class MockLiveSocket implements LiveSocket {
  binaryType: BinaryType = 'arraybuffer'
  onopen: ((ev: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null
  private state = 0
  private readonly timers = new Set<ReturnType<typeof setTimeout>>()
  private briefing: Briefing | undefined
  private round: Round | undefined
  private windowQid: string | null = null
  private windowBytes = 0
  private run = 0

  constructor(url: string) {
    const m = /\/api\/live\/([^/]+)\/(\d+)/.exec(url)
    try {
      this.briefing = getBriefing(m?.[1] ?? '')
      this.round = this.briefing.rounds[Number(m?.[2]) - 1]
    } catch {
      this.briefing = undefined
    }
    this.later(120, () => {
      this.state = 1
      this.onopen?.(new Event('open'))
    })
  }

  get readyState(): number {
    return this.state
  }

  send(data: string | ArrayBufferLike | ArrayBufferView): void {
    if (this.state !== 1) return
    if (typeof data !== 'string') {
      if (this.windowQid) this.windowBytes += data.byteLength
      return // mic audio is only counted, never interpreted
    }
    let msg: { type?: string; ticket?: string; cue?: string; qid?: string }
    try {
      msg = JSON.parse(data)
    } catch {
      return this.fail('bad_message', 'Not JSON.')
    }
    switch (msg.type) {
      case 'start':
        return this.start(msg.ticket ?? '')
      case 'cue':
        return this.cue(msg.cue, msg.qid)
      case 'answer_start':
        return this.answerStart(msg.qid ?? '')
      case 'answer_end':
        return this.answerEnd(msg.qid ?? '')
      case 'stop':
        return this.close(1000, 'stop')
      default:
        return this.fail('bad_message', 'Unknown message.')
    }
  }

  close(code = 1000, reason = ''): void {
    if (this.state === 3) return
    this.state = 3
    this.timers.forEach(clearTimeout)
    this.timers.clear()
    this.run++
    this.onclose?.(new CloseEvent('close', { code, reason, wasClean: code === 1000 }))
  }

  // ---- protocol ----

  private start(ticket: string): void {
    if (!ticket.startsWith('mock-') || ticket === 'mock-fail' || !this.round) {
      this.fail('bad_ticket', 'Bad, expired or reused ticket.')
      this.later(0, () => this.close(4401, 'bad_ticket'))
      return
    }
    this.later(250, () => this.text({ type: 'ready', model: 'gemini-3.8-live (mock)', turnTaking: 'manual' }))
  }

  private cue(cue: string | undefined, qid: string | undefined): void {
    const script = this.round?.script
    if (!script) return this.fail('invalid_state', 'No round.')
    if (cue === 'READ_INSTRUCTION') return this.speak(script.instruction)
    if (cue === 'CLOSE') return this.speak(script.closing)
    const question = cue === 'ASK' ? script.questions.find((q) => q.id === qid) : undefined
    if (question) return this.speak(question.text)
    this.fail('bad_message', 'Unknown cue or question.')
  }

  private answerStart(qid: string): void {
    this.windowQid = qid
    this.windowBytes = 0
  }

  private answerEnd(qid: string): void {
    if (this.windowQid !== qid) return this.fail('invalid_state', 'No open answer window.')
    const heard = this.windowBytes >= MIN_ANSWER_BYTES ? this.answerFor(qid) : ''
    this.windowQid = null
    // Like the real relay: what Live heard is sent once, as a final caption, after the window closes.
    if (heard) this.text({ type: 'caption', role: 'worker', text: heard, final: true })
    this.speak(NEUTRAL_THANKS[this.briefing?.workerLang ?? 'en'] ?? 'Thank you.')
  }

  private answerFor(qid: string): string {
    const b = this.briefing
    const q = this.round?.script.questions.find((x) => x.id === qid)
    const long = b && longAnswer(b.workerLang) // QA flag: a worker who talks for 20 seconds
    if (long) return long
    if (b && isLeadDemo(b) && this.round && q) {
      const first = this.round.n === 1 ? LEAD_ROUND1_ANSWERS[qid] : undefined
      if (first) return first.original
      const step = q.stepIds[0] ? LEAD[q.stepIds[0]] : undefined
      if (step) return step.answer
    }
    return '(mock answer)'
  }

  /**
   * The model speaks `text`: PCM frames with partial captions, sent in a burst (see BURST), the final caption with the
   * last frame of the burst, and turn_complete when the speech would end. Caption text is cumulative for the utterance,
   * as the real relay sends it, and runs ahead of the audio (see CAPTION_FRAMES).
   */
  private speak(text: string): void {
    const run = ++this.run
    const pcm = speechPcm(spokenSeconds(text), RATE, seedOf(text))
    const frame = (RATE * FRAME_MS) / 1000
    const frames = Math.ceil(pcm.length / frame)
    const words = pieces(text)
    const gap = FRAME_MS / BURST
    let i = 0
    let shown = 0
    const complete = () => {
      if (run === this.run && this.state === 1) this.text({ type: 'turn_complete' })
    }
    const tick = () => {
      if (run !== this.run || this.state !== 1) return
      if (i >= frames) {
        this.text({ type: 'caption', role: 'model', text, final: true })
        return void this.later(frames * (FRAME_MS - gap), complete)
      }
      const slice = pcm.subarray(i * frame, (i + 1) * frame)
      const copy = new ArrayBuffer(slice.byteLength)
      new Int16Array(copy).set(slice)
      this.emit(copy)
      const upto = Math.ceil((words.length * Math.min(frames, i + CAPTION_FRAMES)) / frames)
      if (i % CAPTION_FRAMES === 0 && upto > shown) {
        this.text({ type: 'caption', role: 'model', text: words.slice(0, upto).join('').trim(), final: false })
        shown = upto
      }
      i++
      this.later(gap, tick)
    }
    this.later(450, tick) // first-audio latency
  }

  // ---- plumbing ----

  private fail(code: string, message: string): void {
    this.text({ type: 'error', code, message })
  }

  private text(obj: object): void {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(obj) }))
  }

  private emit(buf: ArrayBuffer): void {
    this.onmessage?.(new MessageEvent('message', { data: buf }))
  }

  private later(ms: number, fn: () => void): void {
    const t = setTimeout(() => {
      this.timers.delete(t)
      fn()
    }, ms)
    this.timers.add(t)
  }
}

export const mockSocketFactory: SocketFactory = (url) => new MockLiveSocket(url)
