import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { captureAnswer } from '../../src/audio/capture.ts'
import { CHUNK_SAMPLES, ClipSource, type ClipClock } from '../../src/audio/clipSource.ts'
import { SinkRouter } from '../../src/audio/source.ts'
import { decodeWavTo16k, wavBytes } from '../../src/audio/wav.ts'

/** A clock the test moves by hand; `every` callbacks fire as time passes. */
function manualClock() {
  let now = 0
  const timers = new Set<{ ms: number; next: number; fn: () => void }>()
  const clock: ClipClock = {
    now: () => now,
    every: (ms, fn) => {
      const t = { ms, next: now + ms, fn }
      timers.add(t)
      return () => timers.delete(t)
    },
  }
  const advance = (ms: number) => {
    const end = now + ms
    for (;;) {
      const due = [...timers].filter((t) => t.next <= end).sort((a, b) => a.next - b.next)[0]
      if (!due) break
      now = due.next
      due.next += due.ms
      due.fn()
    }
    now = end
  }
  return { clock, advance, timers }
}

const tone = (samples: number) => Int16Array.from({ length: samples }, (_, i) => Math.round(8000 * Math.sin(i / 3)))

describe('ClipSource: a stored sample answer played into an answer window', () => {
  it('hands over 640-byte chunks at real-time pace: one now, then one per 20 ms, never ahead of the clock', () => {
    const { clock, advance } = manualClock()
    const src = new ClipSource(tone(CHUNK_SAMPLES * 10), { clock, tailMs: 0 })
    const got: Int16Array[] = []
    src.setSink((c) => got.push(c))

    assert.equal(got.length, 1)
    advance(100)
    assert.equal(got.length, 6) // 1 + 100 ms / 20 ms
    assert.ok(got.every((c) => c.byteLength === 640))
  })

  it('a late timer catches up, but no more than its burst limit at once', () => {
    const { clock, advance } = manualClock()
    const src = new ClipSource(tone(CHUNK_SAMPLES * 100), { clock, tailMs: 0, maxBurst: 5 })
    let n = 0
    src.setSink(() => n++)
    // A tab in the background: the 20 ms timer fires once after 400 ms.
    const before = n
    advance(400)
    assert.ok(n - before <= 20, `${n - before} chunks for 400 ms`)
  })

  it('sends the whole clip, pads the last chunk, adds the silent tail, then resolves `done` and stops', async () => {
    const { clock, advance, timers } = manualClock()
    const pcm = tone(CHUNK_SAMPLES * 3 + 100)
    const src = new ClipSource(pcm, { clock, tailMs: 60 })
    const got: Int16Array[] = []
    src.setSink((c) => got.push(c))
    advance(1000)
    await src.done

    assert.equal(got.length, 4 + 3) // 4 clip chunks (the last padded) + 3 x 20 ms of tail
    assert.deepEqual([...got[3]!.subarray(0, 100)], [...pcm.subarray(CHUNK_SAMPLES * 3)])
    assert.ok(got[3]!.subarray(100).every((v) => v === 0))
    assert.ok(got.slice(4).every((c) => c.every((v) => v === 0)))
    assert.equal(timers.size, 0)
  })

  it('stops the moment its sink is released (the window ended), and sends nothing after', () => {
    const { clock, advance } = manualClock()
    const src = new ClipSource(tone(CHUNK_SAMPLES * 50), { clock })
    let n = 0
    src.setSink(() => n++)
    advance(40)
    src.setSink(null)
    const at = n
    advance(500)
    assert.equal(n, at)
  })

  it('feeds the same capture as the mic: the WAV holds exactly the chunks that were forwarded', async () => {
    const { clock, advance } = manualClock()
    const src = new ClipSource(tone(CHUNK_SAMPLES * 20), { clock, tailMs: 40 })
    const forwarded: number[] = []
    const capture = captureAnswer(src, { forward: (c) => forwarded.push(c.byteLength), config: { silenceMs: 30_000 } })
    void src.done.then(() => capture.finish('done'))
    advance(2000)
    const clip = await capture.done

    assert.equal(clip.pcmBytes, forwarded.reduce((a, b) => a + b, 0))
    assert.equal(clip.pcmBytes, (20 + 2) * 640)
    assert.equal(clip.reason, 'done')
  })
})

describe('SinkRouter: the mic feeds an answer window first, a problem report only outside one', () => {
  it('sends a chunk to the main sink when one is set, else to the side sink, never to both', () => {
    const router = new SinkRouter()
    const main: number[] = []
    const side: number[] = []
    router.setSide((c) => side.push(c[0]!))
    router.push(Int16Array.of(1))
    router.setMain((c) => main.push(c[0]!))
    router.push(Int16Array.of(2))
    router.setMain(null)
    router.push(Int16Array.of(3))

    assert.deepEqual(main, [2])
    assert.deepEqual(side, [1, 3])
  })
})

describe('decodeWavTo16k: the stored clip as answer-window PCM', () => {
  it('reads a 16 kHz mono WAV back sample for sample', () => {
    const pcm = tone(1600)
    assert.deepEqual([...(decodeWavTo16k(wavBytes(pcm, 16_000)) ?? [])], [...pcm])
  })

  it('resamples 24 kHz to 16 kHz', () => {
    const out = decodeWavTo16k(wavBytes(tone(24_000), 24_000))
    assert.equal(out?.length, 16_000)
  })

  it('skips a LIST chunk before `data`', () => {
    const plain = wavBytes(Int16Array.of(5, -5, 7), 16_000)
    const list = new Uint8Array([...'LIST'].map((c) => c.charCodeAt(0)).concat([4, 0, 0, 0, 1, 2, 3, 4]))
    const withList = new Uint8Array(plain.length + list.length)
    withList.set(plain.subarray(0, 36))
    withList.set(list, 36)
    withList.set(plain.subarray(36), 36 + list.length)
    assert.deepEqual([...(decodeWavTo16k(withList) ?? [])], [5, -5, 7])
  })

  it('refuses what is not 16-bit PCM WAV', () => {
    assert.equal(decodeWavTo16k(new TextEncoder().encode('not a wav file at all')), null)
  })
})
