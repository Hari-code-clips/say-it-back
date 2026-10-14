import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Mic } from '../../src/audio/mic.ts'
import type { Player } from '../../src/audio/player.ts'
import { LiveSession } from '../../src/live/liveSession.ts'
import { SessionError, type StageEvents } from '../../src/live/session.ts'
import type { LiveSocket } from '../../src/live/socket.ts'

// Gemini Live streams the audio of a turn well ahead of real time and ends the turn (turn_complete) when the speech
// would end. Measured against the real model: a 31 s read-out was on the wire within 8 s, then the socket was silent
// for 24 s. The session's idle watchdog must not read that silence as a dead relay while the speech is still playing.

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

/** A relay that answers the cues like Live: one burst of audio, then `turn_complete` after `quietMs`. */
class BurstRelay implements LiveSocket {
  binaryType: BinaryType = 'arraybuffer'
  readyState = 1
  onopen: LiveSocket['onopen'] = null
  onmessage: LiveSocket['onmessage'] = null
  onclose: LiveSocket['onclose'] = null
  onerror: LiveSocket['onerror'] = null
  private readonly burst: boolean
  private readonly quietMs: number | null

  /** `quietMs` null: never send `turn_complete`. `burst` false: send no audio either. */
  constructor(quietMs: number | null, burst = true) {
    this.quietMs = quietMs
    this.burst = burst
    setTimeout(() => this.onopen?.({} as Event), 0)
  }

  private deliver(data: string | ArrayBuffer, after = 0) {
    setTimeout(() => this.onmessage?.({ data } as MessageEvent), after)
  }

  send(data: string | ArrayBuffer | ArrayBufferView<ArrayBuffer>): void {
    const msg = JSON.parse(String(data)) as { type: string; cue?: string }
    if (msg.type === 'start') this.deliver(JSON.stringify({ type: 'ready', model: 'gemini-3.8-live', turnTaking: 'manual' }))
    else if (msg.type === 'cue' && msg.cue === 'READ_INSTRUCTION') {
      if (this.burst) this.deliver(new ArrayBuffer(4800))
      if (this.quietMs !== null) this.deliver(JSON.stringify({ type: 'turn_complete' }), this.quietMs)
    } else if (msg.type === 'cue') this.deliver(JSON.stringify({ type: 'turn_complete' }), 5)
    else if (msg.type === 'stop') setTimeout(() => this.onclose?.({ code: 1000 } as CloseEvent), 0)
  }

  close(): void {
    this.readyState = 3
  }
}

/** Plays whatever is enqueued for `playMs`, like the real Player's queue. */
function fakePlayer(playMs: number): Player {
  let busyUntil = 0
  return {
    enqueue: () => {
      busyUntil = Date.now() + playMs
    },
    flush: () => {
      busyUntil = 0
    },
    whenIdle: () => sleep(Math.max(0, busyUntil - Date.now())),
    get busy() {
      return Date.now() < busyUntil
    },
  } as unknown as Player
}

const events: StageEvents = { onPhase: () => undefined, onCaption: () => undefined }

function session(relay: BurstRelay, player: Player, idleMs: number): LiveSession {
  return new LiveSession({
    wsUrl: '/api/live/b_abcdefghijkl/1',
    ticket: 'x'.repeat(43),
    questionIds: [],
    mic: { setSink: () => undefined } as unknown as Mic,
    player,
    events,
    openSocket: () => relay,
    location: { protocol: 'http:', host: 'localhost:5173' },
    idleMs,
    stopWaitMs: 20,
    thanksWaitMs: 50,
  })
}

describe('LiveSession idle watchdog', () => {
  it('keeps waiting for turn_complete while the queued speech is still playing', async () => {
    // Audio on the wire at once, 300 ms of silence, turn_complete; the speech plays for 400 ms. idleMs is 80.
    const result = await session(new BurstRelay(300), fakePlayer(400), 80).run()
    assert.equal(result.turnTaking, 'manual')
  })

  it('still fails when the relay is silent and nothing is playing', async () => {
    await assert.rejects(session(new BurstRelay(null, false), fakePlayer(0), 80).run(), (e: unknown) => e instanceof SessionError && e.code === 'timeout')
  })

  it('counts the silence again once the speech has played out', async () => {
    const started = Date.now()
    await assert.rejects(session(new BurstRelay(null), fakePlayer(200), 100).run(), (e: unknown) => e instanceof SessionError && e.code === 'timeout')
    // Not at 100 ms (the idle limit) but after the 200 ms of speech plus one more idle period.
    assert.ok(Date.now() - started >= 180, `failed after ${Date.now() - started} ms`)
  })
})
