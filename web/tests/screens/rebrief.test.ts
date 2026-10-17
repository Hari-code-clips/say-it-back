import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Briefing } from '../../src/api/types.ts'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import { rebriefDraft, recordBar } from '../../src/screens/record/rebrief.ts'

// The record's way on from a No-go on a permit (build-notes/25, "Also"): brief the same worker again on the same permit.
// docs/API.md, "Permit-to-work grouping": a later post for a slot replaces it, so this is a new briefing with the same slot.

type Permitted = Pick<Briefing, 'siteId' | 'taskId' | 'supervisorLang' | 'workerLang' | 'instruction' | 'sop' | 'permit'>

const base: Permitted = {
  siteId: 'sg', taskId: 'lifting-zone', supervisorLang: 'en', workerLang: 'ta', instruction: 'Keep clear of the load.',
  sop: { id: 'SOP-LF-03', version: 'v2', title: 'Lifting zone', text: '...' }, permit: { ref: 'PTW-123', crewSize: 2, slot: 2 },
}
const decided = (value: 'go' | 'no_go', permit: Briefing['permit']) => ({ permit, decision: { value, openStepIds: [], at: '' } })

describe('rebriefDraft', () => {
  it('keeps the permit and the SAME slot (not the next), and starts from the previous instruction', () => {
    const d = rebriefDraft(base)
    assert.deepEqual(d?.permit, { ref: 'PTW-123', crewSize: 2, slot: 2 })
    assert.equal(d?.instruction, 'Keep clear of the load.')
    assert.deepEqual([d?.siteId, d?.taskId, d?.supervisorLang, d?.workerLang], ['sg', 'lifting-zone', 'en', 'ta'])
  })

  it('carries a pasted SOP for a custom task, and nothing else about the worker', () => {
    const d = rebriefDraft({ ...base, taskId: 'custom', sop: { id: 'custom', version: 'v1', title: 'Hot work', text: 'Wet the area first.' } })
    assert.deepEqual([d?.customTitle, d?.customSop], ['Hot work', 'Wet the area first.'])
    assert.deepEqual(Object.keys(d ?? {}).sort(), ['customSop', 'customTitle', 'instruction', 'permit', 'siteId', 'supervisorLang', 'taskId', 'workerLang'])
  })

  it('is null without a permit', () => {
    assert.equal(rebriefDraft({ ...base, permit: null }), null)
  })
})

describe('the record bar', () => {
  it('no permit: a new briefing, or all records', () => {
    assert.deepEqual(recordBar(decided('go', null)), { primary: { kind: 'new' }, secondary: { kind: 'all' } })
    assert.deepEqual(recordBar(decided('no_go', null)), { primary: { kind: 'new' }, secondary: { kind: 'all' } })
  })

  it('Go with workers still to come: the next worker leads', () => {
    assert.deepEqual(recordBar(decided('go', { ref: 'P', crewSize: 3, slot: 1 })), { primary: { kind: 'next', slot: 2, crew: 3 }, secondary: { kind: 'new' } })
  })

  it('Go on the last worker: nothing more on this permit', () => {
    assert.deepEqual(recordBar(decided('go', { ref: 'P', crewSize: 2, slot: 2 })), { primary: { kind: 'new' }, secondary: { kind: 'all' } })
  })

  it('No-go on the LAST worker: brief that worker again is the primary, not a dead end', () => {
    assert.deepEqual(recordBar(decided('no_go', { ref: 'P', crewSize: 2, slot: 2 })), { primary: { kind: 'rebrief', slot: 2 }, secondary: { kind: 'new' } })
  })

  it('No-go on a worker with others to come: the next worker stays the primary, the same worker again sits beside it', () => {
    assert.deepEqual(recordBar(decided('no_go', { ref: 'P', crewSize: 3, slot: 1 })), { primary: { kind: 'next', slot: 2, crew: 3 }, secondary: { kind: 'rebrief', slot: 1 } })
  })

  it('a crew of one: No-go offers the same worker again', () => {
    assert.deepEqual(recordBar(decided('no_go', { ref: 'P', crewSize: 1, slot: 1 })).primary, { kind: 'rebrief', slot: 1 })
  })

  it('the words exist in all three languages, with the worker number', () => {
    for (const table of [en, ta, zh]) {
      assert.match(table['record.rebrief'], /\{n\}/)
      assert.match(table['record.rebriefHint'], /\{n\}/)
    }
    assert.equal(en['record.rebrief'], 'Brief worker {n} again')
  })
})
