import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { Catalog } from '../../src/api/types.ts'
import { TASK_ICONS, taskIcon } from '../../src/api/taskIcons.ts'
import { taskTitle } from '../../src/i18n/catalogText.ts'
import { ICON_NAMES } from '../../src/theme/iconNames.ts'
import catalogJson from '../../src/mock/catalog.json' with { type: 'json' }

const catalog = catalogJson as unknown as Catalog

describe('every catalog task has its own icon and a Chinese title', () => {
  it('maps each task icon id to a symbol of its own, not the generic fallback', () => {
    const unmapped = catalog.tasks.filter((task) => !(task.icon in TASK_ICONS)).map((task) => `${task.id}: ${task.icon}`)
    assert.deepEqual(unmapped, [])
  })

  it('uses only symbols in the Google Fonts subset (ICON_NAMES); any other name would show as plain text', () => {
    const subset = new Set<string>(ICON_NAMES)
    assert.deepEqual(Object.values(TASK_ICONS).filter((name) => !subset.has(name)), [])
    assert.ok(subset.has(taskIcon('an-id-no-one-knows')))
  })

  it('maps the v0.5 held-out tasks: a gas meter for confined space (there is no manhole symbol), roofing for the fragile roof', () => {
    assert.equal(taskIcon('confined'), 'gas_meter')
    assert.equal(taskIcon('roof'), 'roofing')
  })

  it('titles each task in Chinese, which the API catalog does not carry', () => {
    const english = catalog.tasks.filter((task) => taskTitle({ id: task.id, title: { en: task.title.en } }, 'zh') === task.title.en).map((task) => task.id)
    assert.deepEqual(english, [])
  })

  it('has the Chinese titles of the held-out tasks ready before they reach the catalog', () => {
    assert.equal(taskTitle({ id: 'confined-space', title: { en: 'x' } }, 'zh'), '进入受限空间（检修井）')
    assert.equal(taskTitle({ id: 'fragile-roof', title: { en: 'x' } }, 'zh'), '在易碎屋面上作业')
  })
})
