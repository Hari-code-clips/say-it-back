import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { CHUNK_SAMPLES, ClipSource, type ClipClock } from '../../src/audio/clipSource.ts'
import type { ChunkSink, ChunkSource } from '../../src/audio/source.ts'
import { AnswerWindow } from '../../src/live/answerWindow.ts'

class FakeMic implements ChunkSource {
  sink: ChunkSink | null = null
  level = 0
  setSink(sink: ChunkSink | null) {
    this.sink = sink
  }
  speak(n: number) {
    for (let i = 0; i < n; i++) this.sink?.(new Int16Array(CHUNK_SAMPLES).fill(9000))
  }
}

/** Let the window's pending awaits run (the app's timers always come after them). */
const settle = () => new Promise<void>((resolve) => setImmediate(resolve))

function clock(): ClipClock & { tick: (ms: number) => void } {
  let now = 0
  const fns = new Set<() => void>()
  return {
    now: () => now,
    every: (_ms, fn) => {
      fns.add(fn)
      return () => fns.delete(fn)
    },
    tick(ms: number) {
      for (let t = 0; t < ms; t += 20) {
        now += 20
        for (const f of [...fns]) f()
      }
    },
  }
}

describe('AnswerWindow: "Use the sample answer" replaces the mic inside the window', () => {
  it('drops what the mic had, sends the clip on the same path, records it as the WAV and names the question', async () => {
    const mic = new FakeMic()
    const c = clock()
    const win = new AnswerWindow()
    const sent: number[] = []
    const done = win.run('q1', mic, { forward: (chunk) => sent.push(chunk.byteLength) }, (p) => p)
    mic.speak(5) // room noise before the tap: forwarded, then dropped from the WAV

    const sample = new ClipSource(new Int16Array(CHUNK_SAMPLES * 10).fill(4000), { clock: c, tailMs: 40 })
    assert.equal(win.useSample(sample), true)
    assert.equal(mic.sink, null, 'the mic is released before the clip starts')
    mic.speak(3) // nothing reaches the window any more
    await settle()
    c.tick(1000)
    const clip = await done

    assert.equal(clip.pcmBytes, (10 + 2) * 640)
    assert.equal(sent.length, 5 + 12)
    assert.deepEqual(win.sampleAnswers, ['q1'])
    assert.equal(win.open, null)
  })

  it('answers from the mic as before when no sample is used', async () => {
    const mic = new FakeMic()
    const win = new AnswerWindow()
    const done = win.run('q2', mic, {}, (p) => p)
    mic.speak(4)
    win.finish('done')
    const clip = await done
    assert.equal(clip.pcmBytes, 4 * 640)
    assert.deepEqual(win.sampleAnswers, [])
  })

  it('offers no sample when no window is open', () => {
    const win = new AnswerWindow()
    assert.equal(win.useSample(new ClipSource(new Int16Array(10))), false)
  })

  it('"Done" during the sample ends the window early, and the answer still counts as a sample', async () => {
    const mic = new FakeMic()
    const c = clock()
    const win = new AnswerWindow()
    const done = win.run('q1', mic, {}, (p) => p)
    win.useSample(new ClipSource(new Int16Array(CHUNK_SAMPLES * 100).fill(4000), { clock: c }))
    await settle()
    c.tick(100)
    win.finish('done')
    const clip = await done
    assert.equal(clip.reason, 'done')
    assert.ok(clip.pcmBytes < 100 * 640)
    assert.deepEqual(win.sampleAnswers, ['q1'])
  })
})

describe('a sample answer goes only to the question it was tapped for (v0.4 review)', () => {
  it('is refused when another question\'s window is open, and that window keeps the mic', async () => {
    const mic = new FakeMic()
    const win = new AnswerWindow()
    const done = win.run('q2', mic, {}, (p) => p)
    assert.equal(win.useSample(new ClipSource(new Int16Array(CHUNK_SAMPLES * 10)), 'q1'), false)
    assert.notEqual(mic.sink, null, 'the mic still feeds q2')
    mic.speak(3)
    win.finish('done')
    const clip = await done
    assert.equal(clip.pcmBytes, 3 * 640)
    assert.deepEqual(win.sampleAnswers, [])
  })

  it('is accepted for the open window it was tapped for', async () => {
    const mic = new FakeMic()
    const win = new AnswerWindow()
    const done = win.run('q1', mic, {}, (p) => p)
    assert.equal(win.useSample(new ClipSource(new Int16Array(CHUNK_SAMPLES * 2)), 'q1'), true)
    win.finish('done')
    await settle()
    win.finish('done')
    await done
    assert.deepEqual(win.sampleAnswers, ['q1'])
  })
})
