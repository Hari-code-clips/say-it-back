import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { before, describe, it } from 'node:test'
import { Player } from '../../src/audio/player.ts'
import { CaptionPacer } from '../../src/live/captionPacer.ts'
import { installFakeAudio } from '../helpers/fakeAudio.ts'
import { FakeClock } from '../helpers/fakeClock.ts'

// The real thing, replayed: the frames of an 83 s Tamil read-out from the integration run (real gemini-3.8-live through
// the relay), delivered at their recorded times to the real Player on a fake AudioContext clock, with the captions
// paced by CaptionPacer exactly as LiveSession paces them. The audio is 48,000 bytes a second and arrives about 4x
// faster than it plays; the transcription arrives between the audio frames.

interface Frame {
  /** ms after the cue */
  t: number
  /** bytes of one audio frame */
  b?: number
  /** text a partial caption added */
  c?: string
  final?: true
}
const { frames } = JSON.parse(readFileSync(new URL('./readout-frames.json', import.meta.url), 'utf8')) as { frames: Frame[] }

const CUE_AT = 100 // where the cue sits on the fake clock, seconds

interface Run {
  /** When the first audio frame starts to play, and when the last one ends: the read-out, in AudioContext seconds. */
  start: number
  end: number
  text: string
  /** Every caption state shown, when. */
  shown: Array<{ at: number; text: string }>
  /** Per partial caption: when it arrived, where in the audio queue (the pacer's anchor), and the text length after it. */
  captions: Array<{ arrived: number; anchor: number; length: number }>
}

async function replay(): Promise<Run> {
  const clock = new FakeClock()
  const restore = installFakeAudio(clock)
  try {
    const player = new Player()
    await player.start()
    const run: Run = { start: NaN, end: NaN, text: '', shown: [], captions: [] }
    const pacer = new CaptionPacer(clock, (text) => run.shown.push({ at: clock.time, text: text.trim() }))
    for (const f of frames) {
      clock.advanceTo(CUE_AT + f.t / 1000)
      if (f.b !== undefined) {
        if (Number.isNaN(run.start)) run.start = player.nextStart
        player.enqueue(new ArrayBuffer(f.b))
      } else if (f.c !== undefined) {
        run.text += f.c
        run.captions.push({ arrived: clock.time, anchor: player.nextStart, length: run.text.trim().length })
        pacer.frame(run.text, false, player.nextStart)
      } else {
        pacer.frame(run.text.trim(), true, player.nextStart)
      }
    }
    run.end = player.nextStart
    clock.advanceTo(run.end + 5)
    return run
  } finally {
    restore()
  }
}

const quantile = (xs: number[], q: number) => [...xs].sort((a, b) => a - b)[Math.floor(q * (xs.length - 1))]!

describe('the real 83 s read-out, replayed', () => {
  let run: Run
  before(async () => {
    run = await replay()
  })

  it('has the shape the integration run recorded', () => {
    assert.equal(run.captions.length, 80)
    assert.ok(Math.abs(run.end - run.start - 82.79) < 0.01, `${run.end - run.start} s of audio`)
    // The whole transcription is in the browser by 20.6 s, 25 % of the way through the speech: the problem.
    assert.ok(run.captions.at(-1)!.arrived - CUE_AT < 21)
  })

  it('shows the whole text by the time the audio ends, and never before it is all there to show', () => {
    const final = run.text.trim()

    assert.equal(run.shown.at(-1)!.text, final)
    assert.ok(run.shown.at(-1)!.at <= run.end + 0.01, `the last words are shown at ${run.shown.at(-1)!.at - run.start} s of ${run.end - run.start}`)
  })

  it('only ever grows: every state shown is the start of the whole text', () => {
    const final = run.text.trim()

    for (const [i, s] of run.shown.entries()) {
      assert.ok(final.startsWith(s.text), `state ${i} is not a prefix`)
      if (i > 0) assert.ok(s.text.length >= run.shown[i - 1]!.text.length, `state ${i} is shorter than the one before`)
    }
  })

  it('shows no frame before the audio that was queued ahead of it has started to play', () => {
    let seen = 0
    for (const c of run.captions) {
      const first = run.shown.find((s) => s.text.length > seen)!
      assert.ok(first.at >= c.anchor - 0.01, `the words of a frame came ${c.anchor - first.at} s before its anchor`)
      seen = c.length
    }
  })

  it('keeps the caption level with the speech: at 25, 50 and 75 % of the read-out it has shown 25, 50 and 75 % of the text, give or take 4 points', () => {
    const final = run.text.trim().length
    for (const p of [0.25, 0.5, 0.75]) {
      const at = run.start + p * (run.end - run.start)
      const shownChars = run.shown.filter((s) => s.at <= at).at(-1)?.text.length ?? 0
      assert.ok(Math.abs(shownChars / final - p) < 0.04, `at ${p * 100} % of the read-out ${((shownChars / final) * 100).toFixed(1)} % of the text is shown`)
    }
  })

  it('puts each word within about a second of where the speech has it', () => {
    // Where is a word spoken? The wire has no timing, so take the words of a frame to be spoken across the audio that
    // follows the frame (the transcription runs ahead of its audio), up to the next frame. A word's lead is how much
    // earlier than that it is shown, its lag how much later. The same measure for showing frames as they arrive:
    const shownAt = (j: number) => run.shown.find((s) => s.text.length > j)!.at
    const paced: number[] = []
    const onArrival: number[] = []
    const lastFrame: number[] = []
    let from = 0
    for (const [k, c] of run.captions.entries()) {
      const next = run.captions[k + 1]?.anchor ?? run.end
      for (let j = from; j < c.length; j++) {
        const spoken = c.anchor + ((next - c.anchor) * (j - from + 0.5)) / (c.length - from)
        ;(k === run.captions.length - 1 ? lastFrame : paced).push(spoken - shownAt(j))
        onArrival.push(spoken - c.arrived)
      }
      from = c.length
    }
    const stats = (xs: number[]) => ({ lead: Math.max(...xs), lag: -Math.min(...xs), mean: xs.reduce((a, b) => a + b, 0) / xs.length, p95: quantile(xs.map(Math.abs), 0.95) })
    const all = [...paced, ...lastFrame]
    const fmt = (o: Record<string, number>) => Object.entries(o).map(([k, v]) => `${k} ${v.toFixed(2)} s`).join(', ')
    console.log(`  paced, ${all.length} characters:   ${fmt(stats(all))}`)
    console.log(`  paced, but the last frame: ${fmt(stats(paced))}`)
    console.log(`  shown on arrival:           ${fmt(stats(onArrival))}`)

    assert.ok(stats(all).lag < 0.6, 'a word is shown late')
    assert.ok(stats(all).p95 < 1, '95 % of the words are within a second')
    // The last frame adds one word, and the 3.56 s of audio after it is the end of the turn: one word cannot be spread,
    // and how much of that tail is speech is not on the wire. Every other frame leads by at most the audio after it.
    assert.ok(stats(paced).lead < 1.5, `a word leads by ${stats(paced).lead} s`)
    assert.ok(stats(onArrival).lead > 10 * stats(all).lead, 'the replay would not have caught the old behaviour')
  })

  it('keeps the caption near the playhead through the read-out, where showing frames on arrival had it all on screen by a quarter', () => {
    const final = run.text.trim().length
    const progress = (at: number) => (run.shown.filter((s) => s.at <= at).at(-1)?.text.length ?? 0) / final
    const whole = run.shown.find((s) => s.text.length === final)!.at
    const gap = (p: number) => progress(run.start + p * (run.end - run.start)) - p
    console.log(`  whole caption on screen at ${(((whole - run.start) / (run.end - run.start)) * 100).toFixed(1)} % of the read-out; caption minus playback at 25/50/75 %: ${[0.25, 0.5, 0.75].map((p) => (gap(p) * 100).toFixed(1)).join(' / ')} points`)

    assert.ok((whole - run.start) / (run.end - run.start) > 0.9)
  })
})
