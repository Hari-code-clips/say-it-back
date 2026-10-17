import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Briefing, BriefingSummary, Decision } from '../../src/api/types.ts'
import { nextWorkerDraft, permitDraftValid, type Draft } from '../../src/flow/draft.ts'
import { clampSlot, nextOnPermit, permitBoard, permitLabel, permitLink, permitRefValid } from '../../src/lib/permit.ts'

// v0.5.2, docs/API.md "Permit-to-work grouping": one briefing per worker on a high-risk permit, crews of 1 to 6. The slot
// number is the only per-worker field: never a name, ID or nationality (Rule 6).

describe('permitRefValid', () => {
  it('takes 1-32 letters, digits and . _ / - after trimming, as the contract does', () => {
    for (const ok of ['PTW-123', 'a', 'X'.repeat(32), '2026/HW.7_a', '  PTW-1  ']) assert.equal(permitRefValid(ok), true, ok)
  })

  it('refuses anything else', () => {
    for (const bad of ['', '   ', 'X'.repeat(33), 'PTW 123', 'PTW#1', 'ப-1', 'PTW-1;drop']) assert.equal(permitRefValid(bad), false, bad)
  })
})

describe('permitLink', () => {
  it('is the permit to send, trimmed', () => {
    assert.deepEqual(permitLink({ ref: '  PTW-123 ', crewSize: 3, slot: 2 }), { ref: 'PTW-123', crewSize: 3, slot: 2 })
  })

  it('is null outside the contract: crew 1-6, slot 1..crew, a valid number', () => {
    for (const bad of [
      { ref: 'PTW-1', crewSize: 0, slot: 1 },
      { ref: 'PTW-1', crewSize: 7, slot: 1 },
      { ref: 'PTW-1', crewSize: 1.5, slot: 1 },
      { ref: 'PTW-1', crewSize: 3, slot: 0 },
      { ref: 'PTW-1', crewSize: 3, slot: 4 },
      { ref: '', crewSize: 3, slot: 1 },
    ]) assert.equal(permitLink(bad), null, JSON.stringify(bad))
  })
})

describe('permitLabel', () => {
  it('reads "PTW-123 · worker 2 of 3", and the same numbers in Tamil and Chinese', () => {
    const p = { ref: 'PTW-123', crewSize: 3, slot: 2 }
    assert.equal(permitLabel(p, 'en'), 'PTW-123 · worker 2 of 3')
    for (const lang of ['ta', 'zh'] as const) {
      const label = permitLabel(p, lang)
      assert.ok(label.includes('PTW-123') && label.includes('2') && label.includes('3'), label)
      assert.doesNotMatch(label, /\{\w+\}/)
    }
  })
})

describe('the next worker on a permit', () => {
  it('is the next slot, until the last', () => {
    assert.deepEqual(nextOnPermit({ ref: 'P', crewSize: 3, slot: 2 }), { ref: 'P', crewSize: 3, slot: 3 })
    assert.equal(nextOnPermit({ ref: 'P', crewSize: 3, slot: 3 }), null)
    assert.equal(nextOnPermit({ ref: 'P', crewSize: 1, slot: 1 }), null)
  })

  it('keeps the slot inside a smaller crew', () => {
    assert.deepEqual([clampSlot(5, 3), clampSlot(2, 3), clampSlot(0, 3)], [3, 2, 1])
  })
})

const briefing = (over: Partial<Briefing> = {}) =>
  ({
    siteId: 'chennai', taskId: 'scaffold-harness', supervisorLang: 'ta', workerLang: 'hi',
    instruction: 'Clip the harness on before you step up.', sop: { id: 'SOP-WAH-02', version: 'v2', title: 'Work at height', text: '1. Clip on.' },
    permit: { ref: 'PTW-77', crewSize: 3, slot: 1 },
    ...over,
  }) as Briefing

describe('nextWorkerDraft', () => {
  it('starts the next worker with the same site, task, languages and permit, the next slot and the previous instruction', () => {
    assert.deepEqual(nextWorkerDraft(briefing()), {
      siteId: 'chennai', taskId: 'scaffold-harness', supervisorLang: 'ta', workerLang: 'hi',
      customTitle: '', customSop: '', instruction: 'Clip the harness on before you step up.',
      permit: { ref: 'PTW-77', crewSize: 3, slot: 2 },
    })
  })

  it('carries a pasted SOP along', () => {
    const d = nextWorkerDraft(briefing({ taskId: 'custom', sop: { id: 'CUSTOM', version: 'v1', title: 'Valve swap', text: '1. Isolate the line.' } }))
    assert.deepEqual([d?.customTitle, d?.customSop], ['Valve swap', '1. Isolate the line.'])
  })

  it('is null after the last worker, and without a permit', () => {
    assert.equal(nextWorkerDraft(briefing({ permit: { ref: 'PTW-77', crewSize: 3, slot: 3 } })), null)
    assert.equal(nextWorkerDraft(briefing({ permit: null })), null)
    assert.equal(nextWorkerDraft(briefing({ permit: undefined })), null)
  })

  it('carries nothing that could name the worker (Rule 6)', () => {
    const d = nextWorkerDraft(briefing())!
    assert.deepEqual(Object.keys(d).sort(), ['customSop', 'customTitle', 'instruction', 'permit', 'siteId', 'supervisorLang', 'taskId', 'workerLang'])
    assert.deepEqual(Object.keys(d.permit!).sort(), ['crewSize', 'ref', 'slot'])
  })
})

describe('permitDraftValid (the Start screen\'s Continue)', () => {
  const base = { siteId: 'sg', taskId: 'lifting-zone', supervisorLang: 'en', workerLang: 'ta', customTitle: '', customSop: '', instruction: '' } as Draft

  it('lets a draft without a permit through, as before', () => {
    assert.equal(permitDraftValid({ ...base, permit: null }), true)
    assert.equal(permitDraftValid(base), true)
  })

  it('holds a permit block until its number is valid', () => {
    assert.equal(permitDraftValid({ ...base, permit: { ref: '', crewSize: 2, slot: 1 } }), false)
    assert.equal(permitDraftValid({ ...base, permit: { ref: 'PTW 1', crewSize: 2, slot: 1 } }), false)
    assert.equal(permitDraftValid({ ...base, permit: { ref: 'PTW-1', crewSize: 2, slot: 1 } }), true)
  })
})

describe('permitBoard (mock mode only, as the permit-to-work stub would count)', () => {
  const decided = (value: Decision['value'], at: string): Decision => ({ value, openStepIds: [], at })
  const row = (slot: number, decision?: Decision, ref = 'PTW-9'): BriefingSummary =>
    ({ id: `b${slot}${at(decision)}`, permit: { ref, crewSize: 3, slot }, decision }) as BriefingSummary
  const at = (d?: Decision) => d?.at ?? ''

  it('is held until every slot holds a Go, and counts the Go slots', () => {
    const items = [row(1, decided('go', '2026-10-16T10:00:00Z')), row(2, decided('no_go', '2026-10-16T10:10:00Z')), row(3)]
    assert.deepEqual(permitBoard(items, 'PTW-9', 3), { verified: 1, crewSize: 3, status: 'held' })
  })

  it('takes each slot\'s latest decision (a re-brief replaces it), and matches the number case-insensitively', () => {
    // Newest first, as the list (endpoint 5) returns them.
    const items = [
      row(3, decided('no_go', '2026-10-16T10:50:00Z'), 'OTHER'),
      row(3, decided('go', '2026-10-16T10:40:00Z'), 'ptw-9'),
      row(2, decided('go', '2026-10-16T10:30:00Z')),
      row(2, decided('no_go', '2026-10-16T10:10:00Z')),
      row(1, decided('go', '2026-10-16T10:00:00Z')),
    ]
    assert.deepEqual(permitBoard(items, 'ptw-9', 3), { verified: 3, crewSize: 3, status: 'released' })
  })
})
