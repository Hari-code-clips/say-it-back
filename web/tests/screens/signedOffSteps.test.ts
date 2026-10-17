import assert from 'node:assert/strict'
import { after, beforeEach, describe, it } from 'node:test'
import type { ComponentType } from 'react'
import { Router } from 'wouter'
import type { Briefing, SopRef, Step } from '../../src/api/types.ts'
import * as library from '../../src/mock/library.ts'
import * as store from '../../src/mock/store.ts'
import { HttpError } from '../../src/mock/util.ts'
import { buttons, createElement, html, startSsr, visibleText, withUiLang } from '../helpers/ssr.ts'

// Security fixes A (H2, docs/API.md Deviations 2026-10-16): the Steps screen of a briefing started from a signed-off library version
// shows its steps read-only, under one line that says where they were signed off and how they change, and keeps "Confirm and write
// the script". Any other briefing's Steps screen edits, removes and adds as before.

type Props = Record<string, unknown>
const ssr = await startSsr()
after(() => ssr.close())
const { I18nProvider } = await ssr.load<{ I18nProvider: ComponentType<Props> }>('/src/i18n/index.tsx')
const { CatalogProvider } = await ssr.load<{ CatalogProvider: ComponentType<Props> }>('/src/api/catalog.tsx')
const { FeedbackProvider } = await ssr.load<{ FeedbackProvider: ComponentType<Props> }>('/src/ui/FeedbackProvider.tsx')
const { BriefingContext } = await ssr.load<{ BriefingContext: ComponentType<Props> }>('/src/flow/BriefingContext.tsx')
const { StepsScreen, stepsToConfirm } = await ssr.load<{ StepsScreen: ComponentType; stepsToConfirm: (steps: Step[], locked: boolean) => Step[] }>(
  '/src/screens/StepsScreen.tsx',
)

const LIFT = { siteId: 'sg', taskId: 'lifting-zone', supervisorLang: 'en', workerLang: 'ta', instruction: 'Never go under the load.' } as const
const SEED: SopRef = { sopId: 'SOP-LF-03', version: 2 }
const LINE = {
  en: 'Signed off in SOP-LF-03 v2. To change a step, a safety officer signs off a new version.',
  ta: 'SOP-LF-03 v2-இல் உறுதிசெய்யப்பட்டது.',
  zh: '已在 SOP-LF-03 v2 中确认。',
} as const

beforeEach(() => library.resetLibrary())

/** A briefing whose steps endpoint 8 proposed: from the lifting seed, or (no sopRef) from the mock's extraction. */
function proposed(sopRef?: SopRef): Briefing {
  const b = store.createBriefing({ ...LIFT, ...(sopRef ? { sopRef } : {}) })
  return store.extractSteps(b.id)
}

function screen(briefing: Briefing, lang: 'en' | 'ta' | 'zh' = 'en'): string {
  const value = { briefing, setBriefing: () => undefined, refresh: async () => briefing }
  const tree = createElement(I18nProvider, null, createElement(CatalogProvider, null, createElement(FeedbackProvider, null, createElement(BriefingContext, { value }, createElement(StepsScreen)))))
  return withUiLang(lang, () => html(createElement(Router, { ssrPath: `/b/${briefing.id}/steps`, children: tree })))
}

describe('the Steps screen of a signed-off library version (H2)', () => {
  it('says where the steps were signed off and how they change, in one line above the list', () => {
    const markup = screen(proposed(SEED))
    assert.ok(visibleText(markup).includes(LINE.en))
    const line = markup.indexOf('Signed off in SOP-LF-03 v2')
    assert.ok(line > markup.indexOf('Your instruction') && line < markup.indexOf('id="step-s1"'), 'between the instruction and the first step')
  })

  it('shows every step as text, with no field to edit, no remove and no add', () => {
    const b = proposed(SEED)
    const markup = screen(b)
    assert.ok(!markup.includes('<textarea'))
    assert.ok(!buttons(markup).some((x) => /Remove step|Add a step/.test(x.attrs + x.text)))
    for (const s of b.steps) assert.ok(visibleText(markup).includes(s.text), s.id)
  })

  it('keeps the hazard and key points of each step behind its disclosure, and the primary action', () => {
    const b = proposed(SEED)
    const labels = buttons(screen(b)).map((x) => x.text)
    assert.equal(labels.filter((l) => l === 'Hazard and key points').length, b.steps.length)
    assert.ok(labels.includes('Confirm and write the script'))
  })

  it('leaves out the header line that invites editing', () => {
    assert.ok(!visibleText(screen(proposed(SEED))).includes('Edit, remove or add steps'))
  })

  it('names the version in Tamil and Chinese too (drafts)', () => {
    const b = proposed(SEED)
    assert.ok(visibleText(screen(b, 'ta')).includes(LINE.ta))
    assert.ok(visibleText(screen(b, 'zh')).includes(LINE.zh))
  })
})

describe('what Confirm sends (H2)', () => {
  it('a signed-off version’s steps exactly as they came, which the server takes', () => {
    // A step written in the library editor, with no "what the worker must state" (the editor has no such field). Since 17 Oct the
    // sign-off gives it its own text as its essential (build-notes/37), so the signed-off step already carries it.
    const own = library.createSop('sg', { title: 'Lifting, our site', text: 'Our SOP.', taskId: 'lifting-zone' })
    library.setSteps('sg', own.id, 1, [{ id: 's1', text: 'Stay behind the barricade', hazard: '', essential: [], source: 'sop', speakable: true }])
    library.approve('sg', own.id, 1)
    const b = proposed({ sopId: own.id, version: 1 })
    assert.deepEqual(b.steps[0]?.essential, ['Stay behind the barricade'])
    assert.deepEqual(stepsToConfirm(b.steps, true), b.steps)
    assert.equal(store.confirmSteps(b.id, stepsToConfirm(b.steps, true)).status, 'steps_confirmed')
  })

  it('sends a signed-off list as it came, even where the cleaning of other lists would change it', () => {
    // As a version signed off before 17 Oct can still be (none outside a local store): a step with no essentials, and untrimmed text.
    const raw: Step[] = [{ id: 's1', text: ' Stay behind the barricade ', hazard: ' Struck by the load ', essential: [' '], source: 'sop', speakable: true }]
    assert.deepEqual(stepsToConfirm(raw, true), raw)
    assert.notDeepEqual(stepsToConfirm(raw, false), raw)
    assert.deepEqual(stepsToConfirm(raw, false)[0]?.essential, ['Stay behind the barricade'])
  })

  it('a changed signed-off list is still refused: one essential added', () => {
    const own = library.createSop('sg', { title: 'Lifting, our site', text: 'Our SOP.', taskId: 'lifting-zone' })
    library.setSteps('sg', own.id, 1, [{ id: 's1', text: 'Stay behind the barricade', hazard: '', essential: [], source: 'sop', speakable: true }])
    library.approve('sg', own.id, 1)
    const b = proposed({ sopId: own.id, version: 1 })
    const changed = b.steps.map((s) => ({ ...s, essential: [...s.essential, 'and the gate'] }))
    assert.throws(() => store.confirmSteps(b.id, changed), (e: unknown) => e instanceof HttpError && e.code === 'sop_steps_locked')
  })
})

describe('the Steps screen of any other briefing', () => {
  it('edits, removes and adds as before, with no signed-off line', () => {
    const markup = screen(proposed())
    assert.ok(markup.includes('<textarea'))
    assert.ok(buttons(markup).some((x) => x.attrs.includes('Remove step 1')))
    assert.ok(buttons(markup).some((x) => x.text === 'Add a step'))
    assert.ok(visibleText(markup).includes('Edit, remove or add steps') && !visibleText(markup).includes('Signed off in'))
  })
})
