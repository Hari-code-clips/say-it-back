import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { CUSTOM_TASK_ID } from '../../src/api/customTask.ts'
import type { Catalog } from '../../src/api/types.ts'
import { defaultDraft, type Draft } from '../../src/flow/draft.ts'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import catalog from '../../src/mock/catalog.json' with { type: 'json' }
import { START_SECTIONS, startNeed } from '../../src/screens/start/startGate.ts'

// F8 (build-notes/25): the permit block sits right under the task, and a disabled Continue says what is missing.

const draft = (over: Partial<Draft> = {}): Draft => ({ ...defaultDraft(catalog as unknown as Catalog), ...over })

describe('what is missing before Continue (F8)', () => {
  it('nothing, with the defaults', () => {
    assert.equal(startNeed(draft()), null)
  })

  it('a permit with no number says "Enter the permit number"', () => {
    const need = startNeed(draft({ permit: { ref: '  ', crewSize: 2, slot: 1 } }))
    assert.equal(need && en[need.key], 'Enter the permit number')
  })

  it('a permit number outside the contract says to fix it', () => {
    const need = startNeed(draft({ permit: { ref: 'PTW 123!', crewSize: 2, slot: 1 } }))
    assert.equal(need?.key, 'start.need.permitRefInvalid')
  })

  it('a valid permit is nothing missing', () => {
    assert.equal(startNeed(draft({ permit: { ref: 'PTW-123', crewSize: 2, slot: 2 } })), null)
  })

  it('a pasted SOP needs a title first, then the text (with its minimum)', () => {
    const custom = draft({ taskId: CUSTOM_TASK_ID, customTitle: '', customSop: '' })
    assert.equal(startNeed(custom)?.key, 'start.need.customTitle')
    const noText = startNeed({ ...custom, customTitle: 'Hot work' })
    assert.equal(noText?.key, 'start.need.customSop')
    assert.deepEqual(noText?.values, { min: 20 })
    assert.equal(startNeed({ ...custom, customTitle: 'Hot work', customSop: 'x'.repeat(20) }), null)
  })

  it('the sentences exist in all three languages and keep their placeholder', () => {
    for (const key of ['start.need.customTitle', 'start.need.customSop', 'start.need.permitRef', 'start.need.permitRefInvalid'] as const) {
      for (const table of [en, ta, zh]) assert.match(table[key], /\S/)
    }
    for (const table of [en, ta, zh]) assert.match(table['start.need.customSop'], /\{min\}/)
  })
})

describe('the Start screen order (F8)', () => {
  it('lists the task, then the permit, then the site and languages', () => {
    assert.deepEqual([...START_SECTIONS], ['task', 'permit', 'site', 'languages'])
  })

  it('the screen draws them in that order: the permit block comes right after the task section and before the site', () => {
    const source = readFileSync(new URL('../../src/screens/StartScreen.tsx', import.meta.url), 'utf8')
    const at = (needle: string) => {
      const i = source.indexOf(needle)
      assert.ok(i >= 0, `${needle} is on the screen`)
      return i
    }
    assert.ok(at('id="start-task"') < at('<PermitBlock') && at('<PermitBlock') < at('id="start-site"') && at('id="start-site"') < at('id="start-langs"'))
  })
})
