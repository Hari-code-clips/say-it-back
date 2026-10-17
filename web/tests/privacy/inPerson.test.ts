import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { after, describe, it } from 'node:test'
import type { ComponentType, ReactElement } from 'react'
import { Router } from 'wouter'
import type { Briefing } from '../../src/api/types.ts'
import { allowedPhases, awaitsInPersonCheck } from '../../src/flow/phases.ts'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import { WORKER_WORDS } from '../../src/i18n/worker.ts'
import { inPersonOpenSteps } from '../../src/lib/sampleCovered.ts'
import { speechWav } from '../../src/mock/audio.ts'
import { verifyChain } from '../../src/mock/chain.ts'
import * as store from '../../src/mock/store.ts'
import { HttpError } from '../../src/mock/util.ts'
import { decisionGate } from '../../src/screens/result/gates.ts'
import { buttons, createElement, html, startSsr, visibleText, withUiLang } from '../helpers/ssr.ts'

// 2026-10-17, the in-person check (docs/API.md Deviations; build-notes/38-in-person-check.md): a worker who says "Not now" to the
// recording never holds their own permit. The supervisor records an in-person check: Go always needs the reason, every step of the
// round stays open, the decision says `inPerson`, and no model is called. The mock plays it as the backend does; the screens say
// plainly that no AI check was made. Also the two accessibility fixes of note 37 (the worker's h1, the bar's landmark).

type Props = Record<string, unknown>
const ssr = await startSsr()
after(() => ssr.close())
const { I18nProvider } = await ssr.load<{ I18nProvider: ComponentType<Props> }>('/src/i18n/index.tsx')
const { CatalogProvider } = await ssr.load<{ CatalogProvider: ComponentType<Props> }>('/src/api/catalog.tsx')
const { FeedbackProvider } = await ssr.load<{ FeedbackProvider: ComponentType<Props> }>('/src/ui/FeedbackProvider.tsx')
const { BriefingContext } = await ssr.load<{ BriefingContext: ComponentType<Props> }>('/src/flow/BriefingContext.tsx')
const { DecisionScreen } = await ssr.load<{ DecisionScreen: ComponentType }>('/src/screens/DecisionScreen.tsx')
const { RecordScreen } = await ssr.load<{ RecordScreen: ComponentType }>('/src/screens/RecordScreen.tsx')
const { ScriptScreen } = await ssr.load<{ ScriptScreen: ComponentType }>('/src/screens/ScriptScreen.tsx')
const { ConsentDeclined } = await ssr.load<{ ConsentDeclined: ComponentType<Props> }>('/src/screens/brief/ConsentStep.tsx')
const { BriefStage } = await ssr.load<{ BriefStage: ComponentType<Props> }>('/src/screens/brief/BriefStage.tsx')

const REASON = 'Went through every step face to face; he showed me each one.'
const refused = (code: string) => (e: unknown) => e instanceof HttpError && e.code === code

function approvedRound(): string {
  const b = store.createBriefing({
    siteId: 'sg', taskId: 'lifting-zone', supervisorLang: 'en', workerLang: 'ta',
    instruction: "Never go under the load, stay outside the barrier until it's landed, and only follow the signalman.",
  })
  store.confirmSteps(b.id, store.extractSteps(b.id).steps)
  store.createRound(b.id, {})
  store.approveRound(b.id, 1)
  return b.id
}

function declined(): string {
  const id = approvedRound()
  store.recordConsent(id, 1, false)
  return id
}

function screen(briefing: Briefing, path: string, node: ReactElement): string {
  const value = { briefing, setBriefing: () => undefined, refresh: async () => briefing }
  return withUiLang('en', () =>
    html(
      createElement(Router, {
        ssrPath: `/b/${briefing.id}/${path}`,
        children: createElement(I18nProvider, null, createElement(CatalogProvider, null, createElement(FeedbackProvider, null, createElement(BriefingContext, { value }, node)))),
      }),
    ),
  )
}

/** The solid blue fills on a screen, outside the closed confirm dialog: design.md allows exactly one. */
const blueFills = (markup: string) => buttons(markup.replace(/<dialog[\s\S]*?<\/dialog>/g, '')).filter((b) => /\bbg-primary\b/.test(b.attrs))

describe('the rule, as data', () => {
  it('the decision screen opens before any check only while the latest round is declined', () => {
    const id = approvedRound()
    assert.deepEqual(allowedPhases(store.getBriefing(id)), ['script', 'brief'])
    store.recordConsent(id, 1, false)
    const b = store.getBriefing(id)
    assert.equal(awaitsInPersonCheck(b), true)
    assert.deepEqual(allowedPhases(b), ['script', 'brief', 'decision'])
    store.recordConsent(id, 1, true) // the worker agreed after all: the AI check again
    assert.equal(awaitsInPersonCheck(store.getBriefing(id)), false)
  })

  it('every step of the declined round is open, with the steps already open', () => {
    const b = store.getBriefing(declined())
    assert.deepEqual(inPersonOpenSteps(b).map((s) => s.id), b.steps.map((s) => s.id))
    // Round 1 rated every step Got it but s2; the declined round 2 covers s1: s1 (its scope) and s2 (still open) are open.
    const covered = Object.fromEntries(b.steps.map((s) => [s.id, s.id === 's2' ? ('missed' as const) : ('covered' as const)]))
    const later = { ...b, latestVerdicts: covered, rounds: [b.rounds[0]!, { ...b.rounds[0]!, n: 2, stepIds: ['s1'] }] }
    assert.deepEqual(inPersonOpenSteps(later).map((s) => s.id), ['s1', 's2'])
  })

  it('Go always needs the reason after an in-person check, even with no step counted open', () => {
    const base = { choice: 'go' as const, reason: '', openStepCount: 0, goLocked: false }
    assert.equal(decisionGate(base).valid, true)
    assert.equal(decisionGate({ ...base, inPerson: true }).need, 'reason')
    assert.equal(decisionGate({ ...base, inPerson: true, reason: REASON }).valid, true)
    assert.equal(decisionGate({ ...base, inPerson: true, goLocked: true, reason: REASON }).need, 'hazard')
  })
})

describe('the mock backend plays it as the backend does', () => {
  it('records a Go with the reason as an in-person check, every step open, and the record verifies', () => {
    const id = declined()
    assert.throws(() => store.decide(id, { value: 'go' }), refused('reason_required'))
    const b = store.decide(id, { value: 'go', reason: REASON, by: 'Sam' })
    assert.deepEqual([b.status, b.decision?.inPerson, b.decision?.reason], ['decided', true, REASON])
    assert.deepEqual(b.decision?.openStepIds, b.steps.map((s) => s.id))
    const last = b.events?.at(-1)
    assert.deepEqual([last?.type, last?.data.inPerson], ['decided', true])
    assert.equal(store.verify(id).ok, true)
    assert.deepEqual(b.latestVerdicts, {})
  })

  it('finds an edited flag at the decision, either way', () => {
    const b = store.decide(declined(), { value: 'go', reason: REASON })
    assert.equal(verifyChain(b).ok, true)
    const { inPerson: _dropped, ...plain } = b.decision!
    for (const decision of [{ ...b.decision!, inPerson: false }, plain]) {
      assert.deepEqual([verifyChain({ ...b, decision }).reason, verifyChain({ ...b, decision }).brokenAt], ['decision_mismatch', b.events?.at(-1)?.seq])
    }
    const noGo = store.decide(declined(), { value: 'no_go' })
    assert.equal(verifyChain({ ...noGo, decision: { ...noGo.decision!, inPerson: true } }).reason, 'decision_mismatch')
  })

  it('keeps the other rules: no Go before the check without a decline, hazards first, a No-go has no flag', () => {
    const plain = approvedRound()
    assert.throws(() => store.decide(plain, { value: 'go', reason: REASON }), refused('invalid_state'))
    const hazard = declined()
    store.reportHazard(hazard, { round: 1 })
    assert.throws(() => store.decide(hazard, { value: 'go' }), refused('hazard_open'))
    const noGo = store.decide(declined(), { value: 'no_go' })
    assert.equal(noGo.decision?.inPerson, undefined)
    assert.equal(noGo.events?.at(-1)?.data.inPerson, undefined)
  })

  it('takes no audio after the decline, before or after the decision', () => {
    const id = declined()
    const clips = { q1: speechWav(3, 16_000, 7) }
    assert.throws(() => store.checkRound(id, 1, clips, 'turn'), refused('consent_declined'))
    store.decide(id, { value: 'go', reason: REASON })
    assert.throws(() => store.checkRound(id, 1, clips, 'turn'), (e: unknown) => e instanceof HttpError && e.status === 409)
  })

  it('exports the flag in the CSV', () => {
    const id = declined()
    store.decide(id, { value: 'go', reason: REASON })
    const lines = store.csv().trim().split('\n')
    assert.match(lines[0] ?? '', /,inPerson$/)
    assert.ok(lines.filter((l) => l.startsWith(id)).every((l) => l.endsWith(',true')))
  })
})

describe('the screens', () => {
  it('"The worker said not now": the one blue fill records the in-person check; the script is outlined; giving the phone back is quiet', () => {
    const props = { roundLabel: 'Round 1 of 3', onInPerson: () => undefined, onScript: () => undefined, onAskAgain: () => undefined }
    const markup = screen(store.getBriefing(declined()), 'brief', createElement(ConsentDeclined, props))
    assert.deepEqual(blueFills(markup).map((b) => b.text), ['Record an in-person check'])
    const script = buttons(markup).find((b) => b.text === 'Open the script')
    const give = buttons(markup).find((b) => b.text === 'Give phone to worker')
    assert.match(script?.attrs ?? '', /border/)
    assert.match(give?.attrs ?? '', /underline/)
    assert.doesNotMatch(markup, /bg-error|text-error/) // a decline is never a failure
    assert.match(visibleText(markup), /it is no mark against them/)
  })

  it('the decision screen says no AI check was made, needs the reason, and shows the round’s steps with no verdict', () => {
    const b = store.getBriefing(declined())
    const markup = screen(b, 'decision', createElement(DecisionScreen))
    const text = visibleText(markup)
    assert.match(text, /No AI check was made for this worker: they chose not to be recorded\./)
    assert.match(text, /every step of this round stays open/)
    assert.equal((markup.match(/>In person</g) ?? []).length, b.steps.length)
    for (const verdict of ['Got it', 'Ask again', 'Missed', 'Wrong']) assert.ok(!text.includes(verdict), `${verdict} on an in-person check`)
    assert.ok(buttons(markup).some((x) => x.text === 'Back to the script'))
    assert.ok(!text.includes('The tool checked what the worker said back'))
    assert.deepEqual(blueFills(markup).map((x) => x.text), ['Record decision'])
  })

  it('the Script screen offers it while the decline stands, and only then', () => {
    const b = store.getBriefing(declined())
    const markup = screen(b, 'script', createElement(ScriptScreen))
    assert.deepEqual(blueFills(markup).map((x) => x.text), ['Record an in-person check'])
    assert.match(buttons(markup).find((x) => x.text === 'Go to the handover')?.attrs ?? '', /border/)
    assert.match(visibleText(markup), /chose not to be recorded for this round/)
    const plain = screen(store.getBriefing(approvedRound()), 'script', createElement(ScriptScreen))
    assert.ok(!visibleText(plain).includes('Record an in-person check'))
  })

  it('the record says it was checked in person, shows no verdict for the unrated steps, and the round reads "Not recorded"', () => {
    const id = declined()
    const b = store.decide(id, { value: 'go', reason: REASON })
    const text = visibleText(screen(b, 'record', createElement(RecordScreen)))
    assert.match(text, /Checked in person\. The worker chose not to be recorded, so no AI check was made\./)
    assert.match(text, /Not recorded/)
    assert.match(text, /Decision recorded, checked in person/) // the chain timeline's label
    for (const verdict of ['Got it', 'Ask again', 'Missed', 'Wrong']) assert.ok(!text.includes(verdict), `${verdict} on the record`)
  })

  it('the source wires it: the decline is saved again and the briefing re-read before the decision opens', () => {
    const source = readFileSync(new URL('../../src/screens/brief/BriefScreen.tsx', import.meta.url), 'utf8')
    const at = (needle: string) => source.indexOf(needle)
    const start = at('const recordInPerson')
    assert.ok(start > 0)
    const body = source.slice(start)
    assert.ok(body.indexOf('await api.consent(briefing.id, round.n, false)') < body.indexOf('await refresh()'))
    assert.ok(body.indexOf('await refresh()') < body.indexOf('navigate(`/b/${briefing.id}/decision`)'))
  })
})

describe('accessibility (note 37, the moderate findings)', () => {
  it('the worker’s session screen has an h1, in the worker’s language, for a screen reader', () => {
    const words = WORKER_WORDS.ta
    const report = { state: { kind: 'closed' }, level: 0, holds: false, open: () => undefined, speak: () => undefined, tap: () => undefined, finish: () => undefined, retry: () => undefined, cancel: () => undefined, confirmDiscard: () => undefined, keep: () => undefined }
    const hold = { label: 'End round', iconOnly: true, hint: 'Keep holding', confirm: { title: 't', confirmLabel: 'c', cancelLabel: 'x' }, onConfirm: () => undefined }
    const markup = html(
      createElement(BriefStage, { phase: { kind: 'listening', qid: 'q1' }, words, workerTag: 'ta', questionIds: ['q1'], captions: { model: '', worker: '' }, heard: false, getLevel: () => 0, onDone: () => undefined, hold, report }),
    )
    assert.match(markup, new RegExp(`<h1 tabindex="-1" class="sr-only">${words.speak}</h1>`))
  })

  it('the bottom action bar of the decision and record screens is a labelled region, and looks the same', () => {
    const b = store.getBriefing(declined())
    for (const markup of [screen(b, 'decision', createElement(DecisionScreen)), screen(store.decide(b.id, { value: 'go', reason: REASON }), 'record', createElement(RecordScreen))]) {
      assert.match(markup, /<section aria-label="Actions" class="fixed inset-x-0 bottom-0 z-30 border-t border-outline-variant bg-surface pb-\[env\(safe-area-inset-bottom\)\]">/)
    }
    for (const table of [en, ta, zh]) assert.match(table['flow.actions'], /\S/)
  })
})

describe('the words', () => {
  it('exist in all three languages, Tamil and Chinese marked DRAFT for native review', () => {
    for (const table of [en, ta, zh]) assert.match(table['inPerson.record'], /\S/)
    for (const lang of ['ta', 'zh']) {
      const source = readFileSync(new URL(`../../src/i18n/${lang}/inPerson.ts`, import.meta.url), 'utf8')
      assert.match(source, /DRAFT[^\n]*NEEDS NATIVE-SPEAKER REVIEW/)
    }
  })

  it('never put a score or a verdict on the worker', () => {
    const words = Object.entries(en).filter(([k]) => k.startsWith('inPerson.')).map(([, v]) => v)
    for (const w of words) assert.doesNotMatch(w, /\b(score|passed|failed|understood|Got it|Ask again|Missed|Wrong)\b/i, w)
  })
})
