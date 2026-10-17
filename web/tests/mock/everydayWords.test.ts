import assert from 'node:assert/strict'
import { afterEach, describe, it } from 'node:test'
import { demoFor } from '../../src/mock/demos.ts'
import { longAnswer, longInstruction } from '../../src/mock/longScripts.ts'

// The script prompt's rule of 16 Oct (PROMPT_VERSION 2026-10-16.12, build-notes/27-everyday-words.md): the script says the word a worker on
// site says, never an English technical term spelled letter for letter in Tamil script, and no English word left in Latin script. The mock's
// script lines follow it. A worker's ANSWER is not held to it (workers do say those words and the judge accepts them), so only the lines
// the worker HEARS are read here, and the long answer is checked only to be unchanged.

/** English technical terms the mock's Tamil script used to spell out (build-notes/27). */
const SPELLED_OUT = ['டேக் லைன', 'ஐசோலேட்', 'அப்ரூவ்டு', 'லைவ் சோர்ஸ', 'பர்சனல்', 'சுவிட்ச் ஆஃப்', 'ஹார்னஸ', 'லைஃப்லைன', 'கிளிப்', 'லாக்']  // stems: no final pulli
const LATIN = /[A-Za-z]/

const original = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
function flag(value: string): void {
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => value } })
}

afterEach(() => {
  if (original) Object.defineProperty(globalThis, 'localStorage', original)
  else Reflect.deleteProperty(globalThis, 'localStorage')
})

describe('the lifting demo script says the everyday word', () => {
  const demo = demoFor({ taskId: 'lifting-zone', workerLang: 'ta' })!
  const panel = demoFor({ taskId: 'panel-isolation', workerLang: 'ta' })!
  const heard = [...Object.values(demo.steps), ...Object.values(panel.steps)].map((s) => s.sentence)

  it('has no English technical term spelled out in Tamil script, in either demo', () => {
    assert.equal(heard.length, 7)
    for (const sentence of heard) for (const term of SPELLED_OUT) assert.ok(!sentence.includes(term), `${term} in: ${sentence}`)
  })

  it('says padlock, the everyday word, where the panel demo told the worker to lock the breaker', () => {
    assert.ok(panel.steps.s2!.sentence.includes('பூட்டை'))
  })

  it('names the tag line as the rope tied to the load', () => {
    assert.ok(demo.steps.s4!.sentence.includes('கயிற்றால்'))
    assert.match(demo.steps.s4!.sentenceEn, /rope/)
  })

  it("keeps the worker's own words in the answers and quotes", () => {
    assert.ok(demo.steps.s4!.quote.includes('டேக் லைன'))
    assert.ok(panel.steps.s2!.quote.includes('லாக்'))
    assert.ok(demo.reexplainAnswer({ id: 'q3', text: '', backTranslation: '', stepIds: ['s4'] }).original.includes('டேக் லைன'))
  })
})

describe('the long Tamil read-outs say the everyday word', () => {
  for (const [n, count] of [['6', 6], ['21', 21]] as const) {
    it(`has ${count} sentences with no Latin letter and no spelled-out term (flag ${n})`, () => {
      flag(n)
      const lines = longInstruction('ta')!
      assert.equal(lines.length, count)
      for (const line of lines) {
        assert.ok(!LATIN.test(line), `Latin letters in: ${line}`)
        for (const term of SPELLED_OUT) assert.ok(!line.includes(term), `${term} in: ${line}`)
        assert.ok(line.endsWith('.'))
      }
    })
  }

  it("leaves the worker's long answer as the worker says it", () => {
    flag('6')
    assert.ok(longAnswer('ta')!.includes('upstream breaker'))
  })
})
