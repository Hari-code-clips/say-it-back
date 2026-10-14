import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { CaptionPacer, wordEnds } from '../../src/live/captionPacer.ts'
import { FakeClock } from '../helpers/fakeClock.ts'

interface Shown {
  at: number
  text: string
  final: boolean
}

function setup() {
  const clock = new FakeClock()
  const shown: Shown[] = []
  const pacer = new CaptionPacer(clock, (text, final) => shown.push({ at: clock.time, text: text.trimEnd(), final }))
  return { clock, shown, pacer }
}

const near = (actual: number, expected: number, what: string) => assert.ok(Math.abs(actual - expected) < 0.01, `${what}: ${actual} is not near ${expected}`)

describe('wordEnds', () => {
  it('ends each word after the space that follows it, and the last at the end of the text', () => {
    assert.deepEqual(wordEnds('Switch off the breaker'), [7, 11, 15, 22])
  })

  it('keeps punctuation with the word before it', () => {
    assert.deepEqual(wordEnds('Lock it. Test it.'), [5, 9, 14, 17])
  })

  it('finds the words of a Tamil caption between its spaces', () => {
    const text = 'வேலை தொடங்கும் முன் upstream'
    assert.deepEqual(
      wordEnds(text).map((end) => text.slice(0, end).trimEnd()),
      ['வேலை', 'வேலை தொடங்கும்', 'வேலை தொடங்கும் முன்', 'வேலை தொடங்கும் முன் upstream'],
    )
  })

  it('keeps a hyphenated word whole, so the caption never stops at "breaker-"', () => {
    const text = 'உங்கள் lock-ஐ breaker-ல் மாட்டவும்.'

    assert.deepEqual(
      wordEnds(text).map((end) => text.slice(0, end).trimEnd()),
      ['உங்கள்', 'உங்கள் lock-ஐ', 'உங்கள் lock-ஐ breaker-ல்', 'உங்கள் lock-ஐ breaker-ல் மாட்டவும்.'],
    )
  })

  it('splits a script written without spaces into several words, not one', () => {
    const text = '先断开上游断路器并隔离。'
    const ends = wordEnds(text)
    assert.ok(ends.length > 2, `${ends.length} words`)
    assert.equal(ends.at(-1), text.length)
  })

  it('treats a text with no words as one piece', () => {
    assert.deepEqual(wordEnds('...'), [3])
  })
})

describe('CaptionPacer.frame (Live)', () => {
  it('shows a frame when the audio queued before it has played, not when it arrives', () => {
    const { clock, shown, pacer } = setup()

    pacer.frame('one two three', false, 10) // arrived at 0: 10 s of audio were queued ahead of it
    clock.advanceTo(9.99)
    assert.equal(shown.length, 0)
    clock.advanceTo(10)

    assert.deepEqual(shown.map((s) => s.text), ['one'])
  })

  it('spreads the rest of a frame over at least half a second, by the characters before each word', () => {
    const { clock, shown, pacer } = setup()

    pacer.frame('aaaa bbbbbbbb cc', false, 10) // 16 characters; the words start at 0, 5 and 14
    clock.advanceTo(11)

    assert.deepEqual(shown.map((s) => s.text), ['aaaa', 'aaaa bbbbbbbb', 'aaaa bbbbbbbb cc'])
    near(shown[0]!.at, 10, 'first word')
    near(shown[1]!.at, 10 + (0.5 * 5) / 16, 'second word')
    near(shown[2]!.at, 10 + (0.5 * 14) / 16, 'third word')
  })

  it('takes a later frame to last as long as the audio that arrived since the previous one', () => {
    const { clock, shown, pacer } = setup()
    pacer.frame('one two', false, 10)

    pacer.frame('one two three four', false, 12) // 2 s of audio since the last frame
    clock.advanceTo(20)

    const at = (text: string) => shown.find((s) => s.text === text)!.at
    near(at('one two three'), 12, 'three') // the first new word comes out when the audio before the frame has played
    near(at('one two three four'), 12 + (2 * 6) / 10, 'four') // "three " is 6 of the 10 new characters
  })

  it('lets a new frame take over the words of the last one that are still waiting', () => {
    const { clock, shown, pacer } = setup()
    pacer.frame('aaaa bbbb cccc', false, 10) // its words are due at 10, 10.17 and 10.33
    pacer.frame('aaaa bbbb cccc dddd', false, 10.2) // the audio is shorter than the frame was taken to be

    clock.advanceTo(20)

    assert.deepEqual(shown.map((s) => s.text), ['aaaa', 'aaaa bbbb', 'aaaa bbbb cccc dddd'], 'the word still waiting comes out with the first new word')
    near(shown[2]!.at, 10.2, 'the new frame, at the end of the audio queued before it')
  })

  it('shows a final frame in full at the end of the audio, as the final one', () => {
    const { clock, shown, pacer } = setup()
    pacer.frame('one two three', false, 10)

    pacer.frame('one two three', true, 30)
    clock.advanceTo(40)

    assert.deepEqual(shown.at(-1), { at: 30, text: 'one two three', final: true })
    assert.equal(shown.filter((s) => s.final).length, 1)
  })

  it('shows a final frame that no partial announced at once: the whole text is in it, and nothing to follow it by', () => {
    const { clock, shown, pacer } = setup()

    pacer.frame('one two three', true, 30) // the audio queued behind it lasts until 30 s
    clock.advanceTo(0)

    assert.deepEqual(shown, [{ at: 0, text: 'one two three', final: true }])
  })

  it('does not take a stripped final frame for a revision: the words still to come stay scheduled', () => {
    // The relay's partial captions keep the spaces of the raw chunks; its final caption is stripped.
    const { clock, shown, pacer } = setup()
    pacer.frame(' one two three ', false, 10)

    pacer.frame('one two three', true, 30)
    clock.advanceTo(40)

    assert.deepEqual(shown.map((s) => s.text), ['one', 'one two', 'one two three', 'one two three'])
    near(shown[1]!.at, 10 + (0.5 * 4) / 13, 'second word, still on its own time')
  })

  it('replaces the words a revised transcription changed, and no stale one is shown after the revision arrives', () => {
    const { clock, shown, pacer } = setup()
    pacer.frame('Cheque the lock now', false, 10) // none of its words has come out yet

    pacer.frame('Check the lock now and go', false, 10.5) // "Cheque" became "Check"
    clock.advanceTo(20)

    assert.ok(shown.every((s) => !s.text.includes('Cheque')))
    assert.equal(shown.at(-1)!.text, 'Check the lock now and go')
  })

  it('keeps the words before a revision that are still waiting', () => {
    const { clock, shown, pacer } = setup()
    pacer.frame('Switch off the lock now', false, 10)

    pacer.frame('Switch off the block now', false, 10.5) // only "lock" changed
    clock.advanceTo(20)

    const texts = shown.map((s) => s.text)
    assert.ok(texts.includes('Switch off the'), 'the words before the change come out on their own time')
    assert.ok(!texts.some((t) => t.includes('lock now') && !t.includes('block now')))
    assert.equal(texts.at(-1), 'Switch off the block now')
  })

  it('ignores a frame with no text, and one that adds nothing', () => {
    const { clock, shown, pacer } = setup()
    pacer.frame('one two', false, 10)

    pacer.frame('   ', false, 11)
    pacer.frame('one two', false, 11)
    clock.advanceTo(20)

    assert.deepEqual(shown.map((s) => s.text), ['one', 'one two'])
  })

  it('starts the next utterance afresh after a final frame', () => {
    const { clock, shown, pacer } = setup()
    pacer.frame('one two', false, 10)
    pacer.frame('one two', true, 11)

    pacer.frame('three four', false, 12)
    clock.advanceTo(20)

    assert.deepEqual(shown.slice(-2).map((s) => s.text), ['three', 'three four'])
  })
})

describe('CaptionPacer.add (Turn)', () => {
  it('shows text at its time, and at once when the time has passed', () => {
    const { clock, shown, pacer } = setup()
    clock.advanceTo(5)

    pacer.add(4, 'late')
    pacer.add(7, 'later', true)
    clock.advanceTo(5)
    assert.deepEqual(shown.map((s) => s.text), ['late'])
    clock.advanceTo(7)

    assert.deepEqual(shown.map((s) => s.text), ['late', 'later'])
    near(shown[1]!.at, 7, 'later')
  })
})

describe('CaptionPacer.drop and flush', () => {
  it('drop: what was waiting is never shown, and no timer is left', () => {
    const { clock, shown, pacer } = setup()
    pacer.frame('one two three', false, 10)

    pacer.drop()
    clock.advanceTo(100)

    assert.deepEqual(shown, [])
    assert.equal(clock.waiting, 0)
  })

  it('drop: the next frame is not compared with the dropped text', () => {
    const { clock, shown, pacer } = setup()
    pacer.frame('one two', false, 10)
    pacer.drop()

    pacer.frame('three four', false, 5)
    clock.advanceTo(20)

    assert.deepEqual(shown.map((s) => s.text), ['three', 'three four'])
  })

  it('flush: shows the newest waiting text now, once, and leaves nothing to show later', () => {
    const { clock, shown, pacer } = setup()
    pacer.frame('one two three', false, 10)

    pacer.flush()
    clock.advanceTo(100)

    assert.deepEqual(shown.map((s) => s.text), ['one two three'])
    assert.equal(clock.waiting, 0)
  })

  it('flush with nothing waiting shows nothing', () => {
    const { shown, pacer } = setup()
    pacer.flush()
    assert.deepEqual(shown, [])
  })
})
