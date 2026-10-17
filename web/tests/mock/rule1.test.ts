import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Verdict } from '../../src/api/types.ts'
import { demoFor, demoRating, rule1Verdict, type DemoRating } from '../../src/mock/demos.ts'
import { speechWav } from '../../src/mock/audio.ts'
import * as store from '../../src/mock/store.ts'

// Guard rule 1 (API.md v0.5.3), as the mock plays it: passes that agree stand, a contradiction in either pass stands, and every other
// split is "unclear" with `passes_disagreed`. A split is never "covered", and "missed" no longer outranks "unclear".
// The backend's table is backend/tests/test_guards_rule1.py; this is the same 16 pairs.

const VERDICTS: Verdict[] = ['covered', 'unclear', 'missed', 'contradicted']

const TABLE: Record<string, Verdict> = {
  'covered/covered': 'covered',
  'covered/unclear': 'unclear',
  'covered/missed': 'unclear',
  'covered/contradicted': 'contradicted',
  'unclear/covered': 'unclear',
  'unclear/unclear': 'unclear',
  'unclear/missed': 'unclear',
  'unclear/contradicted': 'contradicted',
  'missed/covered': 'unclear',
  'missed/unclear': 'unclear',
  'missed/missed': 'missed',
  'missed/contradicted': 'contradicted',
  'contradicted/covered': 'contradicted',
  'contradicted/unclear': 'contradicted',
  'contradicted/missed': 'contradicted',
  'contradicted/contradicted': 'contradicted',
}

const rated = (verdict: Verdict, judgeB?: Verdict, over: Partial<DemoRating> = {}): DemoRating => ({
  verdict, reason: 'A says so.', confidence: 0.9, quote: 'the worker words', quoteTranslation: 'the worker words', ...(judgeB ? { judgeB } : {}), ...over,
})

describe('mock guard rule 1', () => {
  it('has every one of the 16 pairs in the table, once', () => {
    assert.deepEqual(Object.keys(TABLE).sort(), VERDICTS.flatMap((a) => VERDICTS.map((b) => `${a}/${b}`)).sort())
  })

  for (const [pair, final] of Object.entries(TABLE)) {
    const [a, b] = pair.split('/') as [Verdict, Verdict]
    it(`${a} against ${b} is ${final}${a === b ? '' : ', flagged'}`, () => {
      assert.equal(rule1Verdict(a, b), final)
      const { final: rating, a: passA, b: passB } = demoRating('s1', rated(a, b))
      assert.equal(rating.verdict, final)
      assert.deepEqual(rating.flags, a === b ? [] : ['passes_disagreed'])
      assert.deepEqual([passA.verdict, passB.verdict], [a, b])
    })
  }

  it('a split is never covered', () => {
    for (const a of VERDICTS) for (const b of VERDICTS) if (a !== b) assert.notEqual(rule1Verdict(a, b), 'covered')
  })

  it('a pair with no judge B verdict is a single agreed verdict', () => {
    for (const v of VERDICTS) {
      const { final, b } = demoRating('s1', rated(v))
      assert.deepEqual([final.verdict, final.flags, b.verdict], [v, [], v])
    }
  })

  it('shows the pass that doubted, not the covered pass, next to "Ask again"', () => {
    const covered = demoRating('s1', rated('covered', 'unclear', { reason: 'Every element is stated.', judgeBReason: 'Said to join the wire, but not what clips to it.' }))
    assert.equal(covered.final.verdict, 'unclear')
    assert.equal(covered.final.reason, 'Said to join the wire, but not what clips to it.')
    assert.equal(covered.final.quote, 'the worker words', 'the quote stays: it is what the worker said')

    const missed = demoRating('s1', rated('missed', 'covered', { reason: 'Nothing is said about this step.', judgeBReason: 'Every element is stated.' }))
    assert.equal(missed.final.verdict, 'unclear')
    assert.equal(missed.final.reason, 'Nothing is said about this step.')

    const unclear = demoRating('s1', rated('unclear', 'missed', { reason: 'Said part of it.', judgeBReason: 'Nothing is said.' }))
    assert.equal(unclear.final.reason, 'Said part of it.')
  })

  it('never shows a covered pass\'s sentence beside "Ask again", even when the doubting pass gave none', () => {
    const covered = demoRating('s1', rated('covered', 'unclear', { reason: 'Every element is stated.' }))
    assert.deepEqual([covered.final.verdict, covered.final.reason], ['unclear', ''])
    assert.equal(covered.b.reason, '', 'judge B has no sentence of its own, and does not borrow the covered one')
    const missed = demoRating('s1', rated('missed', 'unclear', { reason: 'Nothing is said about this step.' }))
    assert.deepEqual([missed.final.verdict, missed.final.reason], ['unclear', 'Nothing is said about this step.'])
  })

  it("a contradiction keeps the contradicting pass's own reason", () => {
    const { final } = demoRating('s1', rated('covered', 'contradicted', { reason: 'Covers it.', judgeBReason: 'States an unsafe action.' }))
    assert.deepEqual([final.verdict, final.reason], ['contradicted', 'States an unsafe action.'])
  })
})

describe('mock demos under rule 1', () => {
  it('the lead demo keeps s4 Wrong: judge B said unclear, judge A found the contradiction', () => {
    const s4 = demoFor({ taskId: 'lifting-zone', workerLang: 'ta' })!.round1.s4!
    assert.equal(s4.judgeB, 'unclear')
    const { final } = demoRating('s4', s4)
    assert.deepEqual([final.verdict, final.flags], ['contradicted', ['passes_disagreed']])
  })

  it('the panel demo s3 (judge A missed, judge B unclear) is now Ask again, flagged, not Missed', () => {
    const { final } = demoRating('s3', demoFor({ taskId: 'panel-isolation', workerLang: 'ta' })!.round1.s3!)
    assert.deepEqual([final.verdict, final.flags], ['unclear', ['passes_disagreed']])
  })

  it('a judged panel round carries it through to the round: s3 unclear, the next action is a re-explain', () => {
    const b = store.createBriefing({ siteId: 'sg', taskId: 'panel-isolation', supervisorLang: 'en', workerLang: 'ta', instruction: 'Switch off the breaker, lock it and test it dead.' })
    store.confirmSteps(b.id, store.extractSteps(b.id).steps)
    const round = store.createRound(b.id, {})
    store.approveRound(b.id, 1)
    const clips = Object.fromEntries(round.script.questions.map((q) => [q.id, speechWav(3, 16_000, 7)]))
    const judged = store.checkRound(b.id, 1, clips, 'turn', [])
    const s3 = judged.ratings.find((r) => r.stepId === 's3')!
    assert.deepEqual([s3.verdict, s3.flags], ['unclear', ['passes_disagreed']])
    assert.equal(judged.passA.find((r) => r.stepId === 's3')?.verdict, 'missed')
    assert.equal(judged.passB.find((r) => r.stepId === 's3')?.verdict, 'unclear')
    assert.equal(judged.nextAction, 'reexplain')
  })
})
