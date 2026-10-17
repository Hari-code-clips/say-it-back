import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { after, describe, it } from 'node:test'
import type { ComponentType } from 'react'
import type { Lang } from '../../src/api/types.ts'
import { WORKER_WORDS } from '../../src/i18n/worker.ts'
import { consentStep, needsConsent, type ConsentInput } from '../../src/screens/brief/consentFlow.ts'
import { buttons, createElement, html, icons, startSsr, visibleText } from '../helpers/ssr.ts'

// Privacy, 16 Oct (build-notes/34-privacy.md): before the first answer of a round is recorded, the worker gives or declines consent on
// one calm screen in their own language. "Not now" ends the round kindly. With stored sample answers no voice is recorded, so the
// step is skipped. These tests render the real components and read the HTML back, as tests/screens/workerScreens.test.ts does.

type Props = Record<string, unknown>
const ssr = await startSsr()
after(() => ssr.close())
const { WorkerConsent, WorkerDeclined } = await ssr.load<Record<'WorkerConsent' | 'WorkerDeclined', ComponentType<Props>>>('/src/screens/brief/ConsentStep.tsx')

const LANGS = Object.keys(WORKER_WORDS) as Lang[]
const QIDS = ['q1', 'q2', 'q3']
const input = (over: Partial<ConsentInput> = {}): ConsentInput => ({
  stage: 'worker_ready',
  questionIds: QIDS,
  sampleQids: [],
  consent: 'pending',
  failed: false,
  declinedSeen: false,
  ...over,
})

const report = (holds = false) => ({
  state: { kind: 'closed' },
  level: 0,
  holds,
  open: () => undefined,
  speak: () => undefined,
  tap: () => undefined,
  finish: () => undefined,
  retry: () => undefined,
  cancel: () => undefined,
  confirmDiscard: () => undefined,
  keep: () => undefined,
})
// The supervisor's held buttons, in English: the corner lock (consent screen) and the labelled one (after a decline).
const corner = {
  label: 'Supervisor: hold to take the phone back',
  iconOnly: true,
  holdingLabel: 'Take the phone back',
  hint: 'Keep holding for 1.5 seconds. Only the supervisor takes the phone back.',
  confirm: { title: 'Are you the supervisor?', body: 'The details are for the supervisor.', confirmLabel: 'Yes, show the details', cancelLabel: 'Cancel' },
  onConfirm: () => undefined,
}
const labelled = { ...corner, label: "I'm the supervisor", iconOnly: false, holdingLabel: undefined }
const SUPERVISOR = [corner.label, corner.holdingLabel, corner.hint, corner.confirm.title, corner.confirm.body, corner.confirm.confirmLabel, corner.confirm.cancelLabel, labelled.label]

/** What the worker reads: the supervisor's held button and its dialog taken out. */
function workerText(markup: string): string {
  let text = visibleText(markup)
  for (const s of [...SUPERVISOR].sort((a, b) => b.length - a.length)) text = text.replaceAll(s, ' ')
  return text.replace(/\s+/g, ' ').trim()
}

const consentScreen = (lang: Lang, over: Props = {}) =>
  html(createElement(WorkerConsent, { words: WORKER_WORDS[lang], workerTag: lang, hold: corner, report: report(), busy: false, onAgree: () => undefined, onDecline: () => undefined, ...over }))
const declinedScreen = (lang: Lang) => html(createElement(WorkerDeclined, { words: WORKER_WORDS[lang], workerTag: lang, hold: labelled, report: report() }))

describe('which consent screen the worker_ready stage shows', () => {
  it('asks before the first answer when a person will answer', () => {
    assert.equal(consentStep(input()), 'ask')
  })

  it('skips the step when every question is answered by a stored sample: no human voice is recorded (the evaluator path)', () => {
    assert.equal(needsConsent(QIDS, QIDS), false)
    assert.equal(consentStep(input({ sampleQids: QIDS })), 'none')
  })

  it('still asks when even one question is the worker’s own voice', () => {
    assert.equal(needsConsent(QIDS, ['q1', 'q2']), true)
    assert.equal(consentStep(input({ sampleQids: ['q1', 'q2'] })), 'ask')
  })

  it('shows Start once the worker agreed, and nothing on any other stage', () => {
    assert.equal(consentStep(input({ consent: 'given' })), 'none')
    for (const stage of ['handover', 'worker_running', 'worker_failed', 'recovery', 'handback', 'checking'] as const) {
      assert.equal(consentStep(input({ stage })), 'none')
    }
  })

  it('"Not now" leads the worker to "give the phone to your supervisor", then the supervisor to brief in person', () => {
    assert.equal(consentStep(input({ consent: 'declined' })), 'declined')
    assert.equal(consentStep(input({ consent: 'declined', declinedSeen: true })), 'declined_supervisor')
  })

  it('a choice that could not be saved is a failure the supervisor handles, never a silent Start', () => {
    assert.equal(consentStep(input({ failed: true })), 'failed')
  })
})

describe('the consent screen: one calm screen, one decision, in the worker’s own language', () => {
  for (const lang of LANGS) {
    it(`${lang}: says what is recorded and that the voice is deleted, offers "I agree" and "Not now", and keeps the problem button`, () => {
      const words = WORKER_WORDS[lang]
      const markup = consentScreen(lang)
      const text = workerText(markup)
      assert.ok(text.includes(words.consentWhat) && text.includes(words.consentUse), `${lang}: ${text}`)
      const labels = buttons(markup).map((b) => b.text)
      assert.ok(labels.includes(words.consentAgree), `${lang}: no agree in ${labels.join(' | ')}`)
      assert.ok(labels.includes(words.consentNotNow), `${lang}: no "not now" in ${labels.join(' | ')}`)
      assert.ok(labels.some((l) => l.includes(words.report)), `${lang}: no problem button`)
      assert.ok(!labels.includes(words.start), `${lang}: Start before the worker chose`)
      // Only the worker's language: no English word on a non-Latin worker screen.
      if (lang !== 'en') assert.doesNotMatch(text, /[A-Za-z]{2,}/, `${lang}: English on the worker's screen: ${text}`)
      assert.ok(markup.includes(`lang="${lang}"`))
    })
  }

  it('"I agree" is the one blue fill and "Not now" is outlined, both full width; the heading is what is recorded', () => {
    const markup = consentScreen('ta')
    const words = WORKER_WORDS.ta
    const agree = buttons(markup).find((b) => b.text === words.consentAgree)
    const notNow = buttons(markup).find((b) => b.text === words.consentNotNow)
    assert.match(agree?.attrs ?? '', /bg-primary/)
    assert.doesNotMatch(notNow?.attrs ?? '', /bg-primary|bg-error/)
    assert.match(notNow?.attrs ?? '', /border/)
    assert.match(notNow?.attrs ?? '', /w-full/)
    assert.match(markup, new RegExp(`<h1[^>]*>${words.consentWhat}</h1>`))
    assert.ok(icons(markup).includes('mic'))
  })

  it('has exactly one supervisor control, the held corner lock', () => {
    const markup = consentScreen('ta')
    assert.equal((markup.match(/ data-phase="/g) ?? []).length, 1)
  })

  it('both choices wait while a problem report is held, and while the choice is being saved', () => {
    for (const markup of [consentScreen('ta', { report: report(true) }), consentScreen('ta', { busy: true })]) {
      const words = WORKER_WORDS.ta
      for (const label of [words.consentAgree, words.consentNotNow]) {
        const b = buttons(markup).find((x) => x.text === label)
        assert.match(b?.attrs ?? '', /disabled|aria-disabled="true"/, `${label} is not off: ${b?.attrs}`)
      }
    }
  })

  it('drops the disc under 704 px tall and steps the text down under 640 px (measured: both choices and the problem button on the first screen at 320 x 568 and 375 x 667)', () => {
    const source = readFileSync(new URL('../../src/screens/brief/ConsentStep.tsx', import.meta.url), 'utf8')
    for (const cls of ['[@media(max-height:44rem)]:hidden', '[@media(max-height:44rem)]:gap-4', '[@media(max-height:40rem)]:text-title-md', '[@media(max-height:40rem)]:text-body-lg']) {
      assert.ok(source.includes(cls), `missing ${cls}`)
    }
  })
})

describe('the briefing screen asks before Start (BriefScreen.tsx is state-driven, so its wiring is read from the source)', () => {
  const source = readFileSync(new URL('../../src/screens/brief/BriefScreen.tsx', import.meta.url), 'utf8')

  it('derives the view from consentStep with the round’s questions and the chosen samples', () => {
    assert.match(source, /consentStep\(\{\s*stage,\s*questionIds,\s*sampleQids: sampleQids\(sampleOn, choice\),/)
  })

  it('shows the consent screen, the decline screens and records both choices on the server', () => {
    for (const piece of ["consentView === 'ask'", '<WorkerConsent', "consentView === 'declined'", '<WorkerDeclined', "consentView === 'declined_supervisor'", '<ConsentDeclined']) {
      assert.ok(source.includes(piece), piece)
    }
    assert.match(source, /api\.consent\(briefing\.id, round\.n, true\)/)
    assert.match(source, /api\.consent\(briefing\.id, round\.n, false\)/)
  })

  it('puts the consent screen before Start: its branches come before the worker_ready one', () => {
    assert.ok(source.indexOf("consentView === 'ask'") < source.indexOf("if (stage === 'worker_ready')"))
  })
})

describe('after "Not now": kind, never a failure', () => {
  for (const lang of LANGS) {
    it(`${lang}: thanks the worker and asks for the phone to go to the supervisor, in their language only`, () => {
      const words = WORKER_WORDS[lang]
      const markup = declinedScreen(lang)
      const text = workerText(markup)
      assert.ok(text.includes(words.thanks) && text.includes(words.giveSupervisor), `${lang}: ${text}`)
      if (lang !== 'en') assert.doesNotMatch(text, /[A-Za-z]{2,}/, `${lang}: ${text}`)
      // No warning or error look: a decline is the worker's choice.
      assert.ok(!icons(markup).some((i) => ['error', 'warning', 'report_problem'].includes(i)), icons(markup).join(','))
      assert.doesNotMatch(markup.replace(/<button[\s\S]*?<\/button>/g, ''), /bg-error|text-error/)
    })
  }

  it('the supervisor’s screen after it says nothing was recorded and no mark against the worker, and offers the script', () => {
    const source = readFileSync(new URL('../../src/screens/brief/ConsentStep.tsx', import.meta.url), 'utf8')
    for (const key of ['consent.declinedTitle', 'consent.declinedBody', 'consent.declinedHow', 'consent.toScript', 'brief.give']) assert.ok(source.includes(`'${key}'`), key)
  })
})

describe('the worker’s consent words', () => {
  it('exist, non-empty and distinct, in every worker language (DRAFT, marked for native review)', () => {
    for (const lang of LANGS) {
      const w = WORKER_WORDS[lang]
      const four = [w.consentWhat, w.consentUse, w.consentAgree, w.consentNotNow]
      assert.ok(four.every((s) => s.trim().length > 0), lang)
      assert.equal(new Set(four).size, 4, lang)
    }
    const source = readFileSync(new URL('../../src/i18n/worker.ts', import.meta.url), 'utf8')
    assert.match(source, /consentWhat`, `consentUse`, `consentAgree`, `consentNotNow`: DRAFT/)
  })

  it('say the voice is deleted after the check, within a day (the phone keeps an answer only until it is checked)', () => {
    assert.match(WORKER_WORDS.en.consentUse, /only to check this briefing\. It is deleted after the check, within a day\./)
  })

  it('keep the buttons short enough for one line at 320 px (two words at most)', () => {
    for (const lang of LANGS) {
      for (const label of [WORKER_WORDS[lang].consentAgree, WORKER_WORDS[lang].consentNotNow]) {
        assert.ok(label.length <= 16, `${lang}: "${label}" is long`)
      }
    }
  })
})
