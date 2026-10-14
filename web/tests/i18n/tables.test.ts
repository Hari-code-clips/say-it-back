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

  it('the app never says "approved" or calls the work safe (English)', () => {
    const offenders = Object.entries(en).filter(([, text]) => /approv|all clear|safe to start|marked safe/i.test(text))
    assert.deepEqual(offenders.map(([key]) => key), [])
  })

  it('verdict labels stay the four words of the contract', () => {
    assert.deepEqual(
      [en['verdict.covered'], en['verdict.missed'], en['verdict.contradicted'], en['verdict.unclear']],
      ['Got it', 'Missed', 'Wrong', 'Ask again'],
    )
  })
})
