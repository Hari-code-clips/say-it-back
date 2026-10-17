import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { captureAnswer } from '../../src/audio/capture.ts'
import type { ChunkSink, ChunkSource } from '../../src/audio/source.ts'
import { ReportFlow, holdsPage, type ReportState } from '../../src/screens/brief/reportFlow.ts'

class FakeMic implements ChunkSource {
  sink: ChunkSink | null = null
  level = 0
  setSink(sink: ChunkSink | null) {
    this.sink = sink
  }
  speak(n: number) {
    for (let i = 0; i < n; i++) this.sink?.(new Int16Array(320).fill(9000))
  }
}

const settle = () => new Promise<void>((resolve) => setImmediate(resolve))
/** The flow's state kind, read fresh (an assertion must not narrow a getter that changes). */
const kind = (flow: ReportFlow): string => flow.state.kind

function setup(sendFails: number) {
  const mic = new FakeMic()
  const sent: (Blob | null)[] = []
  const states: ReportState[] = []
  let failures = sendFails
  const flow = new ReportFlow({
    openSource: async () => ({ source: mic, release: async () => undefined }),
    send: async (audio) => {
      sent.push(audio)
      if (failures-- > 0) throw new Error('offline')
    },
    onChange: (s) => states.push(s),
    capture: captureAnswer,
    sentMs: 5,
  })
  return { mic, sent, states, flow }
}

async function recordAndSend(t: ReturnType<typeof setup>) {
  t.flow.open()
  void t.flow.speak()
  await settle()
  t.mic.speak(50) // a second of speech
  t.flow.finish()
  await settle()
  await settle()
}

describe('a failed problem report is never lost (v0.4 review)', () => {
  it('a report that failed to send holds the worker screen', async () => {
    const t = setup(1)
    await recordAndSend(t)
    assert.equal(kind(t.flow), 'failed')
    assert.equal(t.flow.holds, true)
  })

  it('Send again posts the same recording, never a new or empty one', async () => {
    const t = setup(1)
    await recordAndSend(t)
    await t.flow.retry()
    assert.equal(t.sent.length, 2)
    assert.ok(t.sent[0] instanceof Blob && t.sent[0].size > 44)
    assert.equal(t.sent[1], t.sent[0])
    assert.equal(kind(t.flow), 'sent')
    assert.equal(t.flow.holds, false)
  })

  it('it is deleted only through a confirm: cancel asks, Keep it returns it, Delete drops it', async () => {
    const t = setup(1)
    await recordAndSend(t)
    t.flow.cancel()
    assert.equal(kind(t.flow), 'confirm_discard')
    assert.equal(t.flow.holds, true, 'still held while the question is asked')
    t.flow.keep()
    assert.equal(kind(t.flow), 'failed')
    t.flow.cancel()
    t.flow.confirmDiscard()
    assert.equal(kind(t.flow), 'closed')
    assert.equal(t.flow.holds, false)
    assert.equal(t.sent.length, 1, 'deleting sends nothing')
  })

  it('a failed tap is held the same way, and its retry is a tap again', async () => {
    const t = setup(1)
    t.flow.open()
    await t.flow.tap()
    assert.equal(kind(t.flow), 'failed')
    await t.flow.retry()
    assert.deepEqual(t.sent, [null, null])
  })

  it('only recording, sending and an unsent failure hold the page', () => {
    const held = (['opening', 'recording', 'sending', 'failed', 'confirm_discard'] as const).every((kind) => holdsPage({ kind, startedAt: 0, audio: null } as ReportState))
    const free = (['closed', 'choose', 'sent', 'no_mic'] as const).every((kind) => !holdsPage({ kind } as ReportState))
    assert.ok(held && free)
  })
})
