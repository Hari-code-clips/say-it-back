import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { chunkForTts, revealPlan, scriptSentences, sentenceEnds, splitSentences } from '../../src/lib/sentences.ts'

describe('scriptSentences', () => {
  it('treats each line as one sentence, even without punctuation (the backend indexes lines)', () => {
    assert.deepEqual(scriptSentences('Switch off the breaker\nLock it. Tag it.\nTest it'), ['Switch off the breaker', 'Lock it. Tag it.', 'Test it'])
  })

  it('keeps the numbering stable when lines carry stray whitespace', () => {
    assert.deepEqual(scriptSentences('  One. \r\n Two. \n'), ['One.', 'Two.'])
  })

  it('falls back to punctuation for text on a single line', () => {
    assert.deepEqual(scriptSentences('Switch it off. Lock it.'), ['Switch it off.', 'Lock it.'])
    assert.deepEqual(scriptSentences('One sentence only'), ['One sentence only'])
    assert.deepEqual(scriptSentences(''), [])
  })
})

describe('splitSentences', () => {
  it('splits Latin text on . ? !', () => {
    assert.deepEqual(splitSentences('Switch it off. Lock it! Test it?'), ['Switch it off.', 'Lock it!', 'Test it?'])
  })

  it('splits Tamil, Chinese, Hindi/Odia and Burmese sentence ends', () => {
    assert.deepEqual(splitSentences('பிரேக்கரை ஆஃப் செய்யுங்கள். லாக் போடுங்கள்.'), ['பிரேக்கரை ஆஃப் செய்யுங்கள்.', 'லாக் போடுங்கள்.'])
    assert.deepEqual(splitSentences('先断电。再验电。'), ['先断电。', '再验电。'])
    assert.deepEqual(splitSentences('पहले बंद करो। फिर जाँचो।'), ['पहले बंद करो।', 'फिर जाँचो।'])
    assert.deepEqual(splitSentences('ပိတ်ပါ။ စစ်ပါ။'), ['ပိတ်ပါ။', 'စစ်ပါ။'])
  })

  it('keeps text without punctuation as one sentence and drops empties', () => {
    assert.deepEqual(splitSentences('no punctuation here'), ['no punctuation here'])
    assert.deepEqual(splitSentences('   '), [])
  })
})

describe('chunkForTts', () => {
  it('returns short text whole and nothing for blank text', () => {
    assert.deepEqual(chunkForTts('Hello.'), ['Hello.'])
    assert.deepEqual(chunkForTts('  '), [])
  })

  it('packs whole sentences into chunks of at most the limit', () => {
    const sentence = 'This is one sentence of moderate length.'
    const text = Array.from({ length: 30 }, () => sentence).join(' ')

    const chunks = chunkForTts(text, 600)

    assert.ok(chunks.length > 1)
    assert.ok(chunks.every((c) => c.length <= 600))
    assert.ok(chunks.every((c) => c.endsWith('.')))
    assert.equal(chunks.join(' '), text) // nothing lost, nothing duplicated
  })

  it('hard-splits a single sentence that is longer than the limit', () => {
    const long = Array.from({ length: 200 }, (_, i) => `word${i}`).join(' ')

    const chunks = chunkForTts(long, 100)

    assert.ok(chunks.every((c) => c.length <= 100))
    assert.equal(chunks.join(' '), long)
  })
})

describe('chunkForTts: what the server accepts (docs/API.md, endpoint 12)', () => {
  // The server speaks only text that is part of the round's script, whitespace collapsed on both sides.
  const collapse = (text: string) => text.split(/\s+/).filter(Boolean).join(' ')

  it('cuts slices of the text itself: Chinese sentences have no space between them, and none is added', () => {
    const text = Array.from({ length: 30 }, () => '先断开断路器，上锁并挂牌，然后验电确认无电。').join('') // 660 characters on one line

    const chunks = chunkForTts(text)

    assert.ok(chunks.length > 1)
    assert.ok(chunks.every((c) => c.length <= 600 && text.includes(c)))
    assert.equal(chunks.join(''), text, 'nothing lost, nothing added')
  })

  it('gives chunks that are each inside the script once whitespace is collapsed, for a script of one sentence per line', () => {
    const lines = Array.from({ length: 16 }, (_, i) => `Step ${i + 1} is   to do this thing carefully, then check it twice before moving on.`)
    const text = lines.join('\n\n')

    const chunks = chunkForTts(text)

    assert.ok(chunks.length > 1)
    assert.ok(chunks.every((c) => c.length <= 600 && collapse(text).includes(collapse(c))))
    assert.equal(chunks.map(collapse).join(' '), collapse(text), 'every word is spoken once, in order')
  })

  it('keeps stray punctuation at the start of a text, as it is part of the text', () => {
    const text = `!! ${'a'.repeat(40)}. ${'b'.repeat(40)}.`

    assert.deepEqual(chunkForTts(text, 50), [`!! ${'a'.repeat(40)}.`, `${'b'.repeat(40)}.`])
  })

  it('returns a question or a closing, which is spoken whole, as it is', () => {
    assert.deepEqual(chunkForTts('What will you do first before opening the panel?'), ['What will you do first before opening the panel?'])
    assert.deepEqual(chunkForTts('  Thank you.\nPlease wait for your supervisor.  '), ['Thank you.\nPlease wait for your supervisor.'])
  })
})

describe('sentenceEnds', () => {
  it('marks where each sentence ends, so a prefix of the text keeps the script\u2019s line breaks', () => {
    const text = 'Switch off.\nLock it.\nTest it.'

    const ends = sentenceEnds(text)

    assert.deepEqual(ends.map((end) => text.slice(0, end)), ['Switch off.', 'Switch off.\nLock it.', text])
  })

  it('finds the sentences of a single line, and tolerates stray whitespace', () => {
    const text = '  Switch it off.   Lock it. '

    assert.deepEqual(sentenceEnds(text).map((end) => text.slice(0, end).trim()), ['Switch it off.', 'Switch it off.   Lock it.'])
  })

  it('has no ends for blank text', () => {
    assert.deepEqual(sentenceEnds('  \n '), [])
  })
})

describe('revealPlan', () => {
  const three = ['A'.repeat(9) + '.', 'B'.repeat(19) + '.', 'C'.repeat(9) + '.'].join('\n') // 10, 20 and 10 characters

  it('puts each sentence after as much of the clip as the characters before it are of the text', () => {
    const [clip] = revealPlan(three, [three.length])

    assert.deepEqual(clip!.map((s) => s.frac), [0, 10 / 40, 30 / 40]) // 0, 10 and 30 of the 40 characters
  })

  it('shows the text from its start, a line per sentence, and ends on the whole text', () => {
    const [clip] = revealPlan(three, [three.length])

    assert.deepEqual(clip!.map((s) => s.text), ['A'.repeat(9) + '.', 'A'.repeat(9) + '.\n' + 'B'.repeat(19) + '.', three])
    assert.deepEqual(clip!.map((s) => s.final), [false, false, true])
  })

  it('has one step, at the start of the clip, for a one-sentence text', () => {
    assert.deepEqual(revealPlan('What will you do first?', [23]), [[{ frac: 0, text: 'What will you do first?', final: true }]])
  })

  it('shares a long text out over its clips by the characters before each sentence, each step inside its clip', () => {
    const text = Array.from({ length: 4 }, (_, i) => `Sentence ${i}.`).join(' ') // four sentences of 11 characters

    const plan = revealPlan(text, [23, 23])

    assert.deepEqual(plan.map((clip) => clip.length), [2, 2])
    assert.ok(plan.flat().every((s) => s.frac >= 0 && s.frac < 1), 'a sentence is shown before its clip ends')
    assert.equal(plan[1]![0]!.frac, 0, 'the first sentence of the second clip comes up as it starts')
    assert.equal(plan.flat().at(-1)!.text, text)
    assert.equal(plan.flat().filter((s) => s.final).length, 1)
  })

  it('has no steps for blank text', () => {
    assert.deepEqual(revealPlan('', []), [])
    assert.deepEqual(revealPlan('   ', []), [])
  })
})
