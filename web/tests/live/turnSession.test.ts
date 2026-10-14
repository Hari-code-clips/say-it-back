import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Mic } from '../../src/audio/mic.ts'
import type { Player } from '../../src/audio/player.ts'
import { SessionError, type StageEvents } from '../../src/live/session.ts'
import { TurnSession } from '../../src/live/turnSession.ts'
import { partOfScript } from '../../src/mock/util.ts'
import { FakeClock } from '../helpers/fakeClock.ts'

const events: StageEvents = { onPhase: () => undefined, onCaption: () => undefined }
const player = { flush: () => undefined } as unknown as Player
const mic = { setSink: () => undefined } as unknown as Mic

describe('TurnSession', () => {
  it('keeps the error that made a TTS call fail as the cause, so a daily_limit 429 is not shown as "the voice could not be prepared"', async () => {
    const refused = Object.assign(new Error('Today budget is used up.'), { code: 'daily_limit', status: 429 })
    const session = new TurnSession({
      instruction: 'Switch off the breaker. Lock it.',
      questions: [{ id: 'q1', text: 'What will you do first?' }],
      closing: 'Thank you.',
      mic,
      player,
      events,
      tts: async () => {
        throw refused
      },
    })
    await assert.rejects(session.run(), (e: unknown) => {
      assert.ok(e instanceof SessionError)
      assert.equal(e.code, 'tts_failed')
      assert.equal(e.cause, refused)
      return true
    })
  })

  // POST /api/tts speaks only a line of the round's own script (docs/API.md, endpoint 12): inside its instruction, or equal to a question or the closing.
  describe('what it asks the voice to say', () => {
    const closing = 'Thank you. Please wait for your supervisor.'
    const chinese = Array.from({ length: 30 }, () => '先断开断路器，上锁并挂牌，然后验电确认无电。').join('') // 660 characters, no space anywhere
    const english = Array.from({ length: 16 }, (_, i) => `Step ${i + 1} is to do this thing carefully, then check it twice before moving on.`).join('\n')

    for (const [name, instruction] of [['a short script', 'Switch off the breaker.\nLock it.\nTest it dead.'], ['a long Chinese script', chinese], ['a long script of a line per sentence', english]] as const) {
      it(`only sends text the server will accept, for ${name}`, async () => {
        const sent: string[] = []
        const script = { instruction, questions: [], closing }
        const player = { flush: () => undefined, playWav: async (_wav: Blob, onStart?: (start: number, seconds: number) => void) => onStart?.(0, 1) } as unknown as Player
        const session = new TurnSession({
          ...script,
          mic,
          player,
          events,
          clock: new FakeClock(),
          tts: async (text) => {
            sent.push(text)
            return new Blob(['wav'])
          },
        })

        await session.run()

        assert.ok(sent.length >= 2, 'the instruction and the closing')
        assert.deepEqual(sent.filter((text) => !partOfScript(script, text)), [])
        assert.ok(sent.every((text) => text.length <= 600), 'the server takes 600 characters at most')
        assert.ok(sent.includes(closing), 'the closing is spoken whole')
      })
    }
  })
})
