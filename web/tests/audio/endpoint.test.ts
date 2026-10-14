import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { EndpointDetector, rms, type EndReason } from '../../src/audio/endpoint.ts'

const FRAME = 320 // 20 ms at 16 kHz

/** A 20 ms frame of a 200 Hz tone at the given peak level (0..1); silence for 0. */
function frame(level: number): Int16Array {
  const out = new Int16Array(FRAME)
  for (let i = 0; i < FRAME; i++) out[i] = Math.round(Math.sin((2 * Math.PI * 200 * i) / 16_000) * level * 32767)
  return out
}

/** Feeds `count` frames of one level; returns the frame index (1-based) at which the detector ended, if it did. */
function feed(d: EndpointDetector, level: number, count: number): { endedAt: number | null; reason: EndReason | null } {
  for (let i = 1; i <= count; i++) {
    const r = d.push(frame(level))
    if (r) return { endedAt: i, reason: r }
  }
  return { endedAt: null, reason: null }
}

describe('rms', () => {
  it('is 0 for silence and about 0.707 of the peak for a sine', () => {
    assert.equal(rms(new Int16Array(FRAME)), 0)
    assert.ok(Math.abs(rms(frame(1)) - 0.707) < 0.01)
  })
})

describe('EndpointDetector', () => {
  it('ends after about 1.5 s of silence following speech', () => {
    const d = new EndpointDetector()
    assert.equal(feed(d, 0.2, 25).endedAt, null) // 0.5 s of speech

    const end = feed(d, 0, 100)

    assert.equal(end.reason, 'silence')
    assert.equal(end.endedAt, 75) // 75 x 20 ms = 1.5 s
    assert.equal(d.heardSpeech, true)
  })

  it('never ends on silence alone: the cap does, at 30 s', () => {
    const d = new EndpointDetector()

    const end = feed(d, 0, 2000)

    assert.equal(end.reason, 'max')
    assert.equal(end.endedAt, 1500) // 30 s / 20 ms
    assert.equal(d.heardSpeech, false)
  })

  it('does not count a single loud frame (a click) as speech', () => {
    const d = new EndpointDetector()
    feed(d, 0, 10)
    d.push(frame(0.5))

    const end = feed(d, 0, 200)

    assert.equal(end.reason, null) // still waiting for real speech
    assert.equal(d.heardSpeech, false)
  })

  it('ignores steady background noise below the speech threshold', () => {
    const d = new EndpointDetector()
    assert.equal(feed(d, 0.004, 400).endedAt, null)
    assert.equal(d.heardSpeech, false)
  })

  it('a short blip inside the silence does not reset the timer; a real word does', () => {
    const blip = new EndpointDetector()
    feed(blip, 0.2, 25)
    feed(blip, 0, 40)
    blip.push(frame(0.2)) // 20 ms: under the 60 ms blip length
    blip.push(frame(0.2)) // 40 ms
    const endBlip = feed(blip, 0, 100)

    const word = new EndpointDetector()
    feed(word, 0.2, 25)
    feed(word, 0, 40)
    feed(word, 0.2, 5) // 100 ms of speech: resets the silence timer
    const endWord = feed(word, 0, 100)

    assert.equal(endBlip.endedAt, 35) // the blip neither resets nor adds: 40 silent frames before it, 35 after = 75
    assert.equal(endWord.endedAt, 75) // a 100 ms word restarts the 1.5 s count
  })

  it('long loud speech never reads as silence (the adaptive threshold is capped)', () => {
    const d = new EndpointDetector()
    feed(d, 0, 5) // a quiet lead-in, so speech is recognised before the noise floor adapts
    // Then 10 s of continuous speech whose quietest frames (every 50th) are still well above the floor:
    // after 2 s the "noise" minimum is a speech level, and an uncapped threshold would call speech silence.
    let ended: EndReason | null = null
    for (let i = 0; i < 495 && !ended; i++) ended = d.push(frame(i % 50 === 0 ? 0.12 : 0.3))

    assert.equal(ended, null)
    assert.equal(d.heardSpeech, true)
    assert.ok(d.speechMs > 9000)
  })

  it('...and the cap is what guarantees it (without it the same speech ends as "silence")', () => {
    const uncapped = new EndpointDetector({ maxThreshold: Number.POSITIVE_INFINITY })
    feed(uncapped, 0, 5)
    let ended: EndReason | null = null
    for (let i = 0; i < 495 && !ended; i++) ended = uncapped.push(frame(i % 50 === 0 ? 0.12 : 0.3))

    assert.equal(ended, 'silence')
  })

  it('reports speech activity for the UI', () => {
    const d = new EndpointDetector()
    d.push(frame(0.3))
    assert.equal(d.speaking, true)
    d.push(frame(0))
    assert.equal(d.speaking, false)
  })
})
