import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Mic } from '../../src/audio/mic.ts'
import type { Player } from '../../src/audio/player.ts'
import { SessionError, type StageEvents } from '../../src/live/session.ts'
import { TurnSession } from '../../src/live/turnSession.ts'
import { FakeClock } from '../helpers/fakeClock.ts'

// What the supervisor sees in Turn mode: the segment's text comes out a sentence at a time while its clip plays.
// A fake Player plays each clip on a fake clock, so the times are exact; the session runs a round with no questions
// (an instruction and a closing).

interface Setup {
  clock: FakeClock
  shown: Array<{ at: number; text: string; final: boolean }>
  clips: Array<{ start: number; seconds: number }>
  session: TurnSession
}

interface Options {
  /** How long each clip lasts, in play order. */
  seconds: number[]
  /** Runs while the first clip plays, once 30 % of it has. */
  during?: (s: Setup) => void
  /** The first clip breaks once 30 % of it has played. */
  breaks?: boolean
  /** The clock stands still while a clip plays, so its timers are late: the clip is over before they ran. */
  lateTimers?: boolean
}

function setup(instruction: string, closing: string, options: Options): Setup {
  const clock = new FakeClock()
  const shown: Setup['shown'] = []
  const clips: Setup['clips'] = []
  const events: StageEvents = { onPhase: () => undefined, onCaption: (role, text, final) => role === 'model' && shown.push({ at: clock.time, text, final }) }
  const s = { clock, shown, clips } as Setup
  const player = {
    flush: () => undefined,
    async playWav(_wav: Blob, onStart?: (start: number, seconds: number) => void) {
      const length = options.seconds[clips.length] ?? 1
      const start = clock.time + 0.02
      clips.push({ start, seconds: length })
      onStart?.(start, length)
      if (options.lateTimers) return
      if (clips.length === 1 && (options.during || options.breaks)) {
        clock.advanceTo(start + length * 0.3)
        options.during?.(s)
        if (options.breaks) throw new Error('the clip could not be played')
      }
      clock.advanceTo(start + length) // the clip plays out, and its captions with it
    },
  } as unknown as Player
  s.session = new TurnSession({
    instruction,
    questions: [],
    closing,
    mic: { setSink: () => undefined } as unknown as Mic,
    player,
    events,
    tts: async () => new Blob(['wav']),
    clock,
  })
  return s
}

const near = (actual: number, expected: number, what: string, tolerance = 0.01) => assert.ok(Math.abs(actual - expected) < tolerance, `${what}: ${actual} is not near ${expected}`)

describe('TurnSession captions', () => {
  it('reveals a segment a sentence at a time, each as far into the clip as the characters before it are of the text', async () => {
    const text = ['A'.repeat(9) + '.', 'B'.repeat(19) + '.', 'C'.repeat(9) + '.'].join('\n') // 10, 20 and 10 characters
    const { clock, shown, clips, session } = setup(text, 'Thank you.', { seconds: [8] })

    await session.run()

    const [one, two, three] = shown
    assert.equal(one!.at, 0, 'the first sentence is on screen at once')
    assert.equal(one!.text, 'A'.repeat(9) + '.')
    near(two!.at - clips[0]!.start, 0.25 * 8, 'second sentence: 10 of 40 characters before it')
    assert.equal(two!.text, 'A'.repeat(9) + '.\n' + 'B'.repeat(19) + '.', 'one sentence per line, as the script has it')
    near(three!.at - clips[0]!.start, 0.75 * 8, 'third sentence: 30 of 40 characters before it')
    assert.equal(three!.text, text)
    assert.deepEqual(shown.slice(0, 3).map((s) => s.final), [false, false, true])
    assert.ok(clock.time >= clips[0]!.start + 8)
  })

  it('shows a one-sentence closing whole and at once', async () => {
    const { shown, clips, session } = setup('Switch it off.', 'Thank you.', { seconds: [4, 2] })

    await session.run()

    assert.equal(shown.length, 2, 'one caption for each one-sentence segment')
    assert.deepEqual(shown.map((s) => s.text), ['Switch it off.', 'Thank you.'])
    assert.ok(shown.every((s) => s.final))
    assert.equal(shown[1]!.at, clips[0]!.start + 4, 'the closing comes up when the segment starts, before its clip')
  })

  it('times a long segment clip by clip: each clip reveals the sentences it speaks, none after it ends', async () => {
    const text = Array.from({ length: 40 }, (_, i) => `Sentence number ${String(i).padStart(2, '0')}.`).join('\n') // 19 characters each: 30 and 10 per chunk
    const { shown, clips, session } = setup(text, 'Thank you.', { seconds: [20, 10] })

    await session.run()

    assert.equal(clips.length, 3, 'two clips for the instruction, one for the closing')
    const mine = shown.filter((s) => s.text.startsWith('Sentence'))
    assert.equal(mine.length, 40)
    assert.equal(mine.at(-1)!.text, text)
    for (const s of mine.slice(1)) {
      const clip = clips.slice(0, 2).find((c) => s.at >= c.start - 0.001 && s.at < c.start + c.seconds)
      assert.ok(clip, `a sentence shown at ${s.at} is outside the clips of the instruction`)
    }
    // The text is shared out by characters, so the first sentence of the second chunk may come up a hair before its clip.
    near(mine[30]!.at, clips[1]!.start, 'the first sentence of the second chunk, as the clips change', 0.1)
    const inSecond = mine.filter((s) => s.at >= clips[1]!.start - 0.001)
    assert.equal(inSecond.length, 9, 'the rest of that chunk is spread over its own clip')
    assert.ok(inSecond.every((s, i) => i === 0 || s.at > inSecond[i - 1]!.at))
  })

  it('never shows a sentence after the briefing is ended, and leaves no timer', async () => {
    const text = ['One sentence here.', 'Another sentence here.', 'A third sentence here.', 'And a fourth one.'].join('\n')
    const s = setup(text, 'Thank you.', { seconds: [10], during: (it) => it.session.abort() })

    await assert.rejects(s.session.run(), (e: unknown) => e instanceof SessionError && e.code === 'aborted')

    const seen = s.shown.length
    s.clock.advanceTo(100)
    assert.equal(s.shown.length, seen)
    assert.ok(s.shown.length < 4, 'the later sentences were still waiting when it ended')
    assert.equal(s.clock.waiting, 0)
  })

  it('also drops them when the voice breaks, and shows the failure rather than a half-read caption later', async () => {
    const text = ['One sentence here.', 'Another sentence here.', 'A third sentence here.', 'And a fourth one.'].join('\n')
    const s = setup(text, 'Thank you.', { seconds: [10], breaks: true })

    await assert.rejects(s.session.run(), (e: unknown) => e instanceof SessionError && e.code === 'tts_failed')

    const seen = s.shown.length
    s.clock.advanceTo(100)
    assert.equal(s.shown.length, seen)
    assert.equal(s.clock.waiting, 0)
  })

  it('has the whole segment on screen when its clip ends, even if a timer ran late', async () => {
    const text = ['One sentence here.', 'Another sentence here.', 'A third sentence here.'].join('\n')
    const { shown, session } = setup(text, 'Thank you.', { seconds: [6], lateTimers: true })

    await session.run()

    assert.deepEqual(shown.map((s) => s.text), ['One sentence here.', text, 'Thank you.'])
    assert.equal(shown[1]!.final, true)
  })
})
