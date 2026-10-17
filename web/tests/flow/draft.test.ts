import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Catalog } from '../../src/api/types.ts'
import { defaultDraft } from '../../src/flow/draft.ts'
import catalog from '../../src/mock/catalog.json' with { type: 'json' }

describe('the Start screen\'s defaults', () => {
  it('follow the first task\'s demo site and language pair: keep the defaults and the lead demo runs', () => {
    const d = defaultDraft(catalog as unknown as Catalog)
    assert.deepEqual([d.taskId, d.siteId, d.supervisorLang, d.workerLang], ['lifting-zone', 'sg', 'en', 'ta'])
  })

  it('take the first task\'s pair and site even where they are not the site\'s own defaults', () => {
    const c = structuredClone(catalog) as unknown as Catalog
    c.tasks[0]!.demoPair = { supervisorLang: 'zh', workerLang: 'bn' }
    assert.deepEqual([defaultDraft(c).supervisorLang, defaultDraft(c).workerLang], ['zh', 'bn'])
    c.tasks[0]!.demoSite = 'chennai'
    c.tasks[0]!.demoPair = { supervisorLang: 'ta', workerLang: 'hi' }
    const d = defaultDraft(c)
    assert.deepEqual([d.siteId, d.supervisorLang, d.workerLang], ['chennai', 'ta', 'hi'])
  })

  it('fall back to the site\'s defaults when the pair is not offered there', () => {
    const c = structuredClone(catalog) as unknown as Catalog
    c.tasks[0]!.demoPair = { supervisorLang: 'hi', workerLang: 'en' }
    const d = defaultDraft(c)
    assert.deepEqual([d.supervisorLang, d.workerLang], ['en', 'ta'])
  })
})
