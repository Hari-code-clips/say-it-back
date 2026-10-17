import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { EvalGroup, EvalReport } from '../../src/api/types.ts'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import { evalReport } from '../../src/mock/eval.ts'
import { comparisonRows, passBarKey } from '../../src/screens/eval/compare.ts'

// The Eval page's v0.5 evidence (eval report fields, docs/API.md Deviations 2026-10-15): the checker on all items and on
// the held-out tasks beside the keyword baselines, and the pass bar with its condition on correct answers. A report from
// before v0.5 has none of these fields and must still show as it did.

const group = (over: Partial<EvalGroup> = {}): EvalGroup => ({
  n: 20, nItems: 10, exactAccuracy: 0.5, unsafeErrors: 4, unsafeDenominator: 12, unsafeUpperBound95: null,
  catchRate: 0.6, overFlagRate: 0.1, unclearRate: 0.1, correctPassRate: 0.9, ...over,
})

/** A v0.4 report: no correctPassRate, no correctPassMin, no byHeldOut, no baseline. */
function v04(): EvalReport {
  const r = evalReport()
  const { correctPassRate: _c, unsafeUpperBound95Items: _u, unsafeItemDenominator: _d, ...metrics } = r.metrics
  const { byHeldOut: _h, modelOnly: _m, baseline: _b, testsetSha256: _s, ...rest } = r
  return { ...rest, metrics, passBar: { exactAccuracyMin: 0.8, unsafeErrorsMax: 0, passed: true } }
}

describe('comparisonRows', () => {
  it('leaves the table out for a report from before v0.5', () => {
    assert.equal(comparisonRows(v04()), null)
  })

  it('lists the checker on all items, then on the held-out tasks, then both keyword baselines, with their own numbers', () => {
    const report: EvalReport = {
      ...v04(),
      byHeldOut: { heldOut: group({ n: 16, exactAccuracy: 0.75, unsafeErrors: 0 }), inSet: group() },
      baseline: { keyword: group({ unsafeErrors: 9 }), keywordNegation: group({ unsafeErrors: 5 }) },
    }
    const rows = comparisonRows(report)

    assert.deepEqual(Object.keys(rows ?? {}), ['all', 'heldOut', 'keyword', 'keywordNegation'])
    assert.deepEqual(rows?.all, { n: report.nStepRatings, exactAccuracy: report.metrics.exactAccuracy, unsafeErrors: report.metrics.unsafeErrors })
    assert.equal(rows?.heldOut?.exactAccuracy, 0.75)
    assert.deepEqual([rows?.keyword?.unsafeErrors, rows?.keywordNegation?.unsafeErrors], [9, 5])
  })

  it('shows only what the report has: a baseline without a held-out split, and no empty held-out row', () => {
    const report: EvalReport = { ...v04(), byHeldOut: { heldOut: group({ n: 0, nItems: 0, exactAccuracy: null }), inSet: group() }, baseline: { keyword: group() } }

    assert.deepEqual(Object.keys(comparisonRows(report) ?? {}), ['all', 'keyword'])
  })
})

describe('passBarKey', () => {
  it('says the v0.5 bar, with its condition on correct answers, when the report has it', () => {
    assert.equal(passBarKey(evalReport()), 'eval.passBarCorrect')
    assert.equal(passBarKey(v04()), 'eval.passBar')
  })

  it('names all three conditions in every UI language, each with its placeholder', () => {
    for (const table of [en, ta, zh]) {
      for (const slot of ['{acc}', '{unsafe}', '{correct}']) assert.ok(table['eval.passBarCorrect'].includes(slot), slot)
    }
  })
})

describe('the mock report', () => {
  it('carries every v0.5 field, so mock mode shows the held-out and baseline table (labelled illustrative there)', () => {
    const r = evalReport()

    assert.equal(typeof r.metrics.correctPassRate, 'number')
    assert.equal(r.passBar.correctPassMin, 0.75)
    assert.ok(r.byHeldOut && r.modelOnly && r.baseline?.keyword && r.baseline.keywordNegation)
  })
})
