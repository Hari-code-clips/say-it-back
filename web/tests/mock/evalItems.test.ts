import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { rawDemoScript } from '../../src/mock/catalog.ts'
import { MOCK_EVAL_ITEMS, evalReport } from '../../src/mock/eval.ts'

// The mock's sample evaluation items quote the catalog's scripted demo answers, so a reworded answer (v0.5: sg-panel round
// 2 in the SOP's order, test dead after opening and before touching) shows up in mock mode too, never an old copy.

describe('mock evaluation items', () => {
  const byId = (id: string) => MOCK_EVAL_ITEMS.find((i) => i.id === id)

  it('take the panel demo answers, both rounds, from the catalog', () => {
    const rounds = rawDemoScript('sg-panel')?.rounds ?? []
    assert.equal(rounds.length >= 2, true)

    for (const [id, n] of [['panel-isolation.q1.ta.demo.clean.r1', 0], ['panel-isolation.q1.ta.complete.clean', 1]] as const) {
      const item = byId(id)
      assert.equal(item?.answerGloss, rounds[n]?.answer.en, id)
      assert.equal(item?.original, rounds[n]?.answer.ta, id)
    }
  })

  it('no longer has the panel answer that tests for power before opening', () => {
    assert.ok(MOCK_EVAL_ITEMS.every((i) => !/will I open the panel/.test(i.answerGloss)))
  })

  it('names no model in the mock report: its numbers are illustrative', () => {
    assert.deepEqual(Object.keys(evalReport().models), ['mock'])
  })
})
