import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Catalog } from '../../src/api/types.ts'
import { taskPatch } from '../../src/flow/draft.ts'
import catalog from '../../src/mock/catalog.json' with { type: 'json' }

// 17 Oct: a task's stored sample answers exist only for its demo site and pair, so picking the task picks them too.
const c = catalog as unknown as Catalog

describe('picking a task on the Start screen', () => {
  it("also picks the task's demo site and language pair, for every demo suite", () => {
    assert.deepEqual(taskPatch(c, 'telecom-tower'), { taskId: 'telecom-tower', sopRef: null, siteId: 'chennai', supervisorLang: 'ta', workerLang: 'te' })
    assert.deepEqual(taskPatch(c, 'hydro-jetting'), { taskId: 'hydro-jetting', sopRef: null, siteId: 'sg', supervisorLang: 'en', workerLang: 'bn' })
    for (const t of c.tasks) {
      const p = taskPatch(c, t.id)
      assert.equal(p.siteId, t.demoSite, t.id)
      assert.equal(p.workerLang, t.demoPair?.workerLang, t.id)
    }
  })

  it('keeps the site and languages for your own procedure, or a pair its site does not offer', () => {
    assert.deepEqual(taskPatch(c, 'custom'), { taskId: 'custom', sopRef: null })
    const odd = { ...c, tasks: c.tasks.map((t) => (t.id === 'telecom-tower' ? { ...t, demoPair: { supervisorLang: 'ta', workerLang: 'my' } } : t)) } as Catalog
    assert.deepEqual(taskPatch(odd, 'telecom-tower'), { taskId: 'telecom-tower', sopRef: null })
  })
})
