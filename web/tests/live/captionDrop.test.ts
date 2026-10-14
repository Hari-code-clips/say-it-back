import assert from 'node:assert/strict'
import { describe, it, type TestContext } from 'node:test'
import type { Mic } from '../../src/audio/mic.ts'
import type { Player } from '../../src/audio/player.ts'
import { LiveSession } from '../../src/live/liveSession.ts'
import { SessionError, type StageEvents } from '../../src/live/session.ts'
import type { LiveSocket } from '../../src/live/socket.ts'
import { FakeClock } from '../helpers/fakeClock.ts'

// What the worker sees while the model speaks (LiveSession on a fake clock): the model's words come out as the audio
// that follows them plays, the worker's at once, and speech that is cut off takes its words with it.

const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 1))

/** A relay that answers cues with whatever the test delivers. Frames arrive in the order given. */
class Relay implements LiveSocket {
  binaryType: BinaryType = 'arraybuffer'
  readyState = 1
  onopen: LiveSocket['onopen'] = null
  onmessage: LiveSocket['onmessage'] = null
  onclose: LiveSocket['onclose'] = null
  onerror: LiveSocket['onerror'] = null
  onCue: (cue: string) => void = () => undefined
  onAnswerEnd: () => void = () => undefined
  private cues = 0
  private windows = 0
  /** Frames handed over but not yet delivered. */
  private inFlight = 0

  constructor() {
    setTimeout(() => this.onopen?.({} as Event), 0)
  }

  deliver(...frames: Array<object | ArrayBuffer>): void {
    for (const f of frames) {
      this.inFlight++
      setTimeout(() => {
        this.inFlight--
        this.onmessage?.({ data: f instanceof ArrayBuffer ? f : JSON.stringify(f) } as MessageEvent)
      }, 0)
    }
  }

  /** Until every frame sent so far has reached the session, and the session has acted on it. */
  async settle(): Promise<void> {
    await tick() // the session reacts to what was just done, and may hand over more frames
    while (this.inFlight) await tick()
    await tick()
  }

  /** Until the session has opened an answer window. */
  async afterAnswerStart(): Promise<void> {
    while (!this.windows) await tick()
    await this.settle()
  }

  /** Until the session has sent its `n`th cue and the frames answering it have been delivered. */
  async afterCue(n = 1): Promise<void> {
    while (this.cues < n) await tick()
    await this.settle()
  }

  send(data: string | ArrayBuffer | ArrayBufferView<ArrayBuffer>): void {
    const msg = JSON.parse(String(data)) as { type: string; cue?: string }
    if (msg.type === 'start') this.deliver({ type: 'ready', model: 'gemini-3.8-live', turnTaking: 'manual' })
    else if (msg.type === 'cue') {
      this.cues++
      this.onCue(msg.cue ?? '')
    } else if (msg.type === 'answer_start') this.windows++
    else if (msg.type === 'answer_end') this.onAnswerEnd()
    else if (msg.type === 'stop') setTimeout(() => this.onclose?.({ code: 1000 } as CloseEvent), 0)
  }

  close(): void {
    this.readyState = 3
  }

  /** The network dies. */
  lose(): void {
    this.readyState = 3
    this.onclose?.({ code: 1006 } as CloseEvent)
  }
}

/** The Player's queue on the fake clock: audio plays back to back, 48,000 bytes a second. */
function fakePlayer(clock: FakeClock): Player {
  let end = 0
  const nextStart = () => Math.max(clock.time + 0.02, end)
  return {
    get currentTime() {
      return clock.time
    },
    get nextStart() {
      return nextStart()
    },
    get busy() {
      return end > clock.time
    },
    enqueue(frame: ArrayBuffer) {
      end = nextStart() + frame.byteLength / 48_000
    },
    flush() {
      end = 0
    },
    whenIdle: () => (end > clock.time ? new Promise<void>((resolve) => clock.later((end - clock.time) * 1000, resolve)) : Promise.resolve()),
  } as unknown as Player
}

const SECOND = 48_000
const audio = (seconds: number) => new ArrayBuffer(seconds * SECOND)
const model = (text: string, final = false) => ({ type: 'caption', role: 'model', text, final })

/** `t.after` ends the session even when an assertion throws first, so a failing test cannot leave timers running. */
function setup(t: TestContext, questionIds: string[] = []) {
  const clock = new FakeClock()
  const relay = new Relay()
  const shown: Array<{ role: string; text: string; at: number }> = []
  const events: StageEvents = { onPhase: () => undefined, onCaption: (role, text) => shown.push({ role, text: text.trim(), at: clock.time }) }
  const session = new LiveSession({
    wsUrl: '/api/live/b_abcdefghijkl/1',
    ticket: 'x'.repeat(43),
    questionIds,
    mic: { setSink: () => undefined } as unknown as Mic,
    player: fakePlayer(clock),
    events,
    openSocket: () => relay,
    location: { protocol: 'http:', host: 'localhost:5173' },
    idleMs: 60_000,
    stopWaitMs: 20,
    thanksWaitMs: 50,
    clock,
  })
  const run = session.run()
  run.catch(() => undefined)
  t.after(() => session.abort())
  // The first cue (READ_INSTRUCTION) gets two seconds of audio and a caption, which is still waiting for it to play.
  relay.onCue = (cue) => {
    if (cue === 'READ_INSTRUCTION') relay.deliver(audio(2), model('alpha beta gamma delta'))
    else relay.deliver({ type: 'turn_complete' })
  }
  return { clock, relay, shown, session, run, models: () => shown.filter((s) => s.role === 'model') }
}

describe('LiveSession captions', () => {
  it('shows the model’s words as the audio that follows them plays, and the worker’s at once', async (t) => {
    const { clock, relay, shown, session, run, models } = setup(t)
    await relay.afterCue()
    relay.deliver({ type: 'caption', role: 'worker', text: 'நான் ஆஃப் பண்ணுவேன்', final: true })
    await relay.settle()

    assert.deepEqual(shown.map((s) => `${s.role}: ${s.text}`), ['worker: நான் ஆஃப் பண்ணுவேன்'], 'the worker is heard at once, the model is not shown yet')
    clock.advanceTo(2.02 - 0.01)
    assert.deepEqual(models(), [], 'the audio queued before the caption has not finished playing')
    clock.advanceTo(2.6)
    assert.equal(models().at(-1)?.text, 'alpha beta gamma delta')
    assert.ok(models()[0]!.at >= 2.02 - 0.01)

    session.abort()
    await assert.rejects(run, (e: unknown) => e instanceof SessionError && e.code === 'aborted')
  })

  it('drops the words that are waiting when the speech is interrupted (barge-in)', async (t) => {
    const { clock, relay, run, session, models } = setup(t)
    await relay.afterCue()

    relay.deliver({ type: 'interrupted' })
    await relay.settle()
    clock.advanceTo(60)

    assert.deepEqual(models(), [])
    assert.equal(clock.waiting, 0, 'no timer is left to show them')
    relay.deliver({ type: 'turn_complete' })
    await relay.settle()
    session.abort()
    await assert.rejects(run)
  })

  it('drops the words that are waiting when the briefing is ended', async (t) => {
    const { clock, relay, run, session, models } = setup(t)
    await relay.afterCue()

    session.abort()
    clock.advanceTo(60)

    await assert.rejects(run, (e: unknown) => e instanceof SessionError && e.code === 'aborted')
    assert.deepEqual(models(), [])
    assert.equal(clock.waiting, 0)
  })

  it('drops the words that are waiting when the connection closes', async (t) => {
    const { clock, relay, run, models } = setup(t)
    await relay.afterCue()

    relay.lose()
    clock.advanceTo(60)

    await assert.rejects(run, (e: unknown) => e instanceof SessionError && e.code === 'socket_closed')
    assert.deepEqual(models(), [])
    assert.equal(clock.waiting, 0)
  })

  it('has the whole text on screen when the audio has played out, and keeps nothing for the next segment', async (t) => {
    const { clock, relay, run, models } = setup(t)
    await relay.afterCue()

    relay.deliver({ type: 'turn_complete' })
    await relay.settle() // the session now waits for the two seconds of audio to play out
    clock.advanceTo(2.02)
    await relay.settle()

    assert.equal(models().at(-1)?.text, 'alpha beta gamma delta')
    assert.equal(clock.waiting, 0, 'nothing is left over for the next cue to find')
    const before = models().length
    clock.advanceTo(60)
    assert.equal(models().length, before, 'and nothing of that segment is shown later')

    await run // the closing cue runs on, with no caption of its own
  })

  it('shows nothing late from one segment once the next has started', async (t) => {
    const { clock, relay, run, models } = setup(t)
    await relay.afterCue()
    relay.deliver({ type: 'turn_complete' })
    await relay.settle()
    clock.advanceTo(2.02) // the audio has played out, and the caption is complete
    await relay.settle()

    relay.deliver(model('alpha beta gamma delta epsilon')) // a frame of that segment, late, in the pause before the next cue
    await relay.settle()
    const complete = models().length
    await relay.afterCue(2) // the closing cue has started
    clock.advanceTo(60)

    assert.equal(models().length, complete)
    await run
  })

  it('treats the thanks after an answer as a segment of its own', async (t) => {
    const { clock, relay, session, run, models } = setup(t, ['q1'])
    relay.onCue = (cue) => {
      if (cue === 'READ_INSTRUCTION') relay.deliver(audio(2), model('alpha beta gamma delta'), { type: 'turn_complete' })
      else if (cue === 'ASK') relay.deliver(audio(1), model('one two three'), { type: 'turn_complete' })
      else relay.deliver({ type: 'turn_complete' })
    }
    relay.onAnswerEnd = () => relay.deliver(audio(1), model('thanks now'), model('thanks now', true), { type: 'turn_complete' })
    await relay.afterCue()
    clock.advanceTo(2.02) // the instruction has played out
    await relay.afterCue(2) // the question is asked
    clock.advanceTo(3.1) // and has played out
    await relay.afterAnswerStart() // the worker is answering

    relay.deliver(model('one two three four five')) // a late frame of the question, whose words wait for audio that has played
    await relay.settle()
    session.finishAnswer() // the thanks starts: nothing of the question may come up after this
    await relay.settle()
    clock.advanceTo(60)
    await relay.settle()

    const texts = models().map((m) => m.text)
    assert.ok(!texts.some((x) => x.includes('four')), 'nothing of the question comes up after the worker has answered')
    assert.equal(texts.at(-1), 'thanks now')
    assert.equal(clock.waiting, 0)
    await run
  })
})
