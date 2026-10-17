import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'

const placeholders = (s: string): string[] => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1] ?? '').sort()
const tables = { ta, zh } as const

describe('string tables', () => {
  it('Tamil and Chinese define exactly the English keys', () => {
    const keys = Object.keys(en).sort()
    assert.deepEqual(Object.keys(ta).sort(), keys)
    assert.deepEqual(Object.keys(zh).sort(), keys)
  })

  for (const [name, table] of Object.entries(tables)) {
    it(`${name}: every string keeps the placeholders of the English one`, () => {
      const wrong = Object.entries(en).filter(([key, text]) => placeholders(text).join() !== placeholders((table as Record<string, string>)[key] ?? '').join())
      assert.deepEqual(wrong.map(([key]) => key), [])
    })

    it(`${name}: no empty strings`, () => {
      assert.deepEqual(Object.entries(table).filter(([, v]) => !v.trim()).map(([k]) => k), [])
    })
  }

  // The supervisor approving the SCRIPT (product rule 4: safety content is approved before anyone hears it; build-notes/25 F1 names the
  // button "Approve script") is not the AI approving work (rule 2). Only these three lines may say it; "approved" itself stays banned
  // everywhere by rule2.test.ts, and the Tamil and Chinese UI keep to "confirm" (their banned words are in rule2.test.ts).
  const SUPERVISOR_APPROVES_THE_SCRIPT = new Set(['script.approve', 'script.approvalRecorded', 'error.script_not_approved'])

  it('the app never says "approved" or calls the work safe (English)', () => {
    const offenders = Object.entries(en).filter(([key, text]) => /approv|all clear|safe to start|marked safe/i.test(text) && !SUPERVISOR_APPROVES_THE_SCRIPT.has(key))
    assert.deepEqual(offenders.map(([key]) => key), [])
  })

  it('the three lines that may say "approve" are the supervisor approving the script, and nothing else', () => {
    assert.deepEqual(
      [en['script.approve'], en['script.approvalRecorded'], en['error.script_not_approved']],
      ['Approve script', 'Your approval was recorded at {time}.', 'Nothing is spoken until you approve the script. Go back to the script and approve it there.'],
    )
    assert.ok([...SUPERVISOR_APPROVES_THE_SCRIPT].every((key) => key.startsWith('script.') || key === 'error.script_not_approved'))
  })

  it('verdict labels stay the four words of the contract', () => {
    assert.deepEqual(
      [en['verdict.covered'], en['verdict.missed'], en['verdict.contradicted'], en['verdict.unclear']],
      ['Got it', 'Missed', 'Wrong', 'Ask again'],
    )
  })
})
