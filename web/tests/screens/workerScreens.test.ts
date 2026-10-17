import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { after, describe, it } from 'node:test'
import type { ComponentType } from 'react'
import { WORKER_WORDS } from '../../src/i18n/worker.ts'
import type { Lang } from '../../src/api/types.ts'
import { buttons, createElement, html, icons, startSsr, visibleText } from '../helpers/ssr.ts'

// F2 of build-notes/25: from the moment the worker holds the phone until hand-back, the screen shows only worker-language text, icons,
// the single action (Start, Done) and the red problem button. The supervisor has ONE control, a held button in a corner. These tests
// render the real components and read the HTML back.

type Props = Record<string, unknown>
const ssr = await startSsr()
after(() => ssr.close())
const { WorkerReady, WorkerFailed, WorkerHandBack } = await ssr.load<Record<'WorkerReady' | 'WorkerFailed' | 'WorkerHandBack', ComponentType<Props>>>('/src/screens/brief/WorkerScreens.tsx')
const { BriefStage } = await ssr.load<Record<'BriefStage', ComponentType<Props>>>('/src/screens/brief/BriefStage.tsx')

const LANGS = Object.keys(WORKER_WORDS) as Lang[]

const report = {
  state: { kind: 'closed' },
  level: 0,
  holds: false,
  open: () => undefined,
  speak: () => undefined,
  tap: () => undefined,
  finish: () => undefined,
  retry: () => undefined,
  cancel: () => undefined,
  confirmDiscard: () => undefined,
  keep: () => undefined,
}
// The supervisor's strings, in English: the held buttons' labels, hints and the dialogs they open for a screen reader.
// The corner lock of Start and the session (build-notes/28, refinement a): icon-only; its label is its accessible name and tooltip,
// and `holdingLabel` shows beside it only while it is held.
const HINT = 'Keep holding for 1.5 seconds. Only the supervisor takes the phone back.'
const corner = {
  label: 'Hold to end round',
  iconOnly: true,
  holdingLabel: 'End round',
  hint: 'Keep holding for 1.5 seconds to end the round.',
  confirm: { title: 'End this round?', body: "The worker's answers so far are discarded. You can start the round again.", confirmLabel: 'End round', cancelLabel: 'Cancel' },
  onConfirm: () => undefined,
}
// The failure screen keeps a labelled button: there the supervisor has to find it at once.
const hold = {
  label: "I'm the supervisor",
  hint: 'Keep holding for 1.5 seconds. Only the supervisor takes the phone back.',
  confirm: { title: 'Are you the supervisor?', body: 'The details of what went wrong are for the supervisor, not the worker.', confirmLabel: 'Yes, show the details', cancelLabel: 'Cancel' },
  onConfirm: () => undefined,
}
const HOLD_TO_CONTINUE = 'Supervisor: hold to continue'
// F3: the supervisor takes the phone back with a held button too (same hint), with its own dialog for assistive technology.
const haveHold = {
  label: HOLD_TO_CONTINUE,
  hint: HINT,
  confirm: { title: 'Is the phone back with you?', body: 'The result of the check is for the supervisor, not the worker.', confirmLabel: 'Yes, I have the phone', cancelLabel: 'Cancel' },
  onConfirm: () => undefined,
}
const SUPERVISOR_STRINGS = [
  hold.label, hold.hint, hold.confirm.title, hold.confirm.body, hold.confirm.confirmLabel, hold.confirm.cancelLabel,
  corner.label, corner.holdingLabel, corner.hint, corner.confirm.title, corner.confirm.body, corner.confirm.confirmLabel,
  haveHold.label, haveHold.confirm.title, haveHold.confirm.body, haveHold.confirm.confirmLabel,
]
// What the dialogs' own buttons say (they are in the markup, closed, for assistive technology).
const DIALOG_BUTTONS = [hold.confirm.cancelLabel, hold.confirm.confirmLabel, corner.confirm.confirmLabel, haveHold.confirm.confirmLabel]

const where = (lang: Lang) => ({ words: WORKER_WORDS[lang], workerTag: lang })
const phases = [
  { kind: 'connecting' },
  { kind: 'speaking', segment: 'instruction' },
  { kind: 'speaking', segment: 'question', qid: 'q1' },
  { kind: 'listening', qid: 'q1' },
  { kind: 'finishing' },
] as const
const stage = (lang: Lang, phase: (typeof phases)[number]) =>
  html(
    createElement(BriefStage, {
      ...where(lang),
      phase,
      questionIds: ['q1', 'q2'],
      captions: { model: '', worker: '' },
      heard: false,
      getLevel: () => 0,
      onDone: () => undefined,
      hold: corner,
      report,
    }),
  )

/** Everything a person could read on the screen, without the supervisor's held button and its dialog. */
function workerText(markup: string): string {
  let text = visibleText(markup)
  // Longest first: "Yes, I have the phone" must go before "I have the phone" or a stray "Yes," is left behind.
  for (const s of [...SUPERVISOR_STRINGS].sort((a, b) => b.length - a.length)) text = text.replaceAll(s, ' ')
  return text.replace(/\s+/g, ' ').trim()
}

/** Class names as written (React escapes `&` and `>` in an attribute, and the arbitrary variants are full of them). */
const unescape = (markup: string) => markup.replaceAll('&amp;', '&').replaceAll('&gt;', '>').replaceAll('&#x27;', "'")

/** The screen's controls by what they say (the corner lock's text while held, "End round", is not part of its name). */
const labels = (markup: string) => buttons(markup).map((b) => b.text.replace(` ${corner.holdingLabel}`, ''))

function assertWorkerOnly(markup: string, lang: Lang, allowed: string[], what: string): void {
  // 1. No control but the ones this screen is allowed to have, and none that is an icon-only button (the old X had only an aria-label).
  for (const b of buttons(markup)) {
    if (DIALOG_BUTTONS.includes(b.text)) continue // the dialog's two buttons
    assert.ok(allowed.some((a) => b.text.includes(a)), `${what} (${lang}): unexpected button "${b.text}"`)
    assert.ok(!/aria-label=/.test(b.attrs), `${what} (${lang}): an icon-only button: ${b.attrs}`)
  }
  // 2. No supervisor chrome: the old close X, the mode chip, the English status line, the sample button, the word "ticket".
  const icn = icons(markup)
  assert.ok(!icn.includes('close'), `${what} (${lang}): the close button is back`)
  const text = workerText(markup)
  for (const banned of ['Live voice', 'Turn by turn', 'sample', 'Sample', 'Connecting', 'Listening', 'ticket', 'End this']) {
    assert.ok(!text.includes(banned), `${what} (${lang}): "${banned}" in: ${text}`)
  }
  // 3. Nothing is written in the supervisor's language: no Latin word in a non-Latin worker language.
  if (lang !== 'en') assert.doesNotMatch(text, /[A-Za-z]{2,}/, `${what} (${lang}): English on a worker screen: ${text}`)
  // 4. At most one supervisor control: the held button, a lock.
  assert.ok((markup.match(/ data-phase="/g) ?? []).length <= 1, `${what} (${lang}): more than one held button`)
}

describe('worker screens: only the worker language, icons, the one action and the problem button', () => {
  for (const lang of LANGS) {
    const w = WORKER_WORDS[lang]

    it(`${lang}: Start`, () => {
      const markup = html(createElement(WorkerReady, { ...where(lang), hold: corner, report, onStart: () => undefined }))
      assertWorkerOnly(markup, lang, [w.start, w.report, corner.label], 'ready')
      assert.deepEqual(labels(markup).filter((l) => !SUPERVISOR_STRINGS.includes(l)), [w.start, w.report])
      assert.ok(workerText(markup).includes(w.start))
    })

    for (const phase of phases) {
      it(`${lang}: the session, ${phase.kind}${'segment' in phase ? ` ${phase.segment}` : ''}`, () => {
        const markup = stage(lang, phase)
        const allowed = phase.kind === 'listening' ? [w.done, corner.label] : [w.report, corner.label]
        assertWorkerOnly(markup, lang, allowed, phase.kind)
        // One word says what to do, in the worker's language; the supervisor's status line is gone.
        const word = phase.kind === 'listening' ? w.speak : phase.kind === 'speaking' ? w.listen : w.wait
        assert.ok(workerText(markup).includes(word), `${lang} ${phase.kind}: "${word}"`)
        // Done is the single action while answering; outside an answer window the problem button is the only other control.
        assert.deepEqual(labels(markup).filter((l) => !SUPERVISOR_STRINGS.includes(l)), phase.kind === 'listening' ? [w.done] : [w.report])
      })
    }

    it(`${lang}: a failure says "give the phone to your supervisor", in the worker's language, with a picture, and nothing of the failure`, () => {
      const markup = html(createElement(WorkerFailed, { ...where(lang), hold, report }))
      assertWorkerOnly(markup, lang, [w.report, hold.label], 'failure')
      assert.ok(workerText(markup).includes(w.giveSupervisor), `${lang}: ${workerText(markup)}`)
      assert.deepEqual(icons(markup).filter((i) => ['smartphone', 'arrow_forward', 'groups'].includes(i)), ['smartphone', 'arrow_forward', 'groups'])
      // No recovery action, no reason: those are the supervisor's, behind the held button.
      for (const gone of ['Try again', 'Retry', 'Turn', 'turn by turn', 'stopped', 'could not']) assert.ok(!workerText(markup).includes(gone), gone)
      assert.deepEqual(labels(markup).filter((l) => !SUPERVISOR_STRINGS.includes(l)), [w.report])
    })

    it(`${lang}: after the last answer it says "give the phone back", and the result is not here`, () => {
      const markup = html(createElement(WorkerHandBack, { ...where(lang), report, haveThePhone: haveHold }))
      const text = workerText(markup)
      assert.ok(text.includes(w.handBack), `${lang}: ${text}`)
      // The worker's one control is the problem button; the supervisor's quiet hold is the only other.
      assert.deepEqual(labels(markup).filter((l) => !SUPERVISOR_STRINGS.includes(l)), [w.report])
      assert.ok(labels(markup).includes(HOLD_TO_CONTINUE))
      if (lang !== 'en') assert.doesNotMatch(text, /[A-Za-z]{2,}/)
      for (const gone of ['Re-explain', 'Decide', 'Go', 'No-go']) assert.ok(!text.includes(gone), gone)
    })
  }
})

describe('the supervisor’s one control on a worker screen', () => {
  const ready = () => html(createElement(WorkerReady, { ...where('ta'), hold: corner, report, onStart: () => undefined }))
  const failed = () => html(createElement(WorkerFailed, { ...where('ta'), hold, report }))
  const handBack = (lang: Lang = 'ta') => html(createElement(WorkerHandBack, { ...where(lang), report, haveThePhone: haveHold }))

  it('is a held button with a lock in the corner of Start, the session and a failure, and exactly one per screen', () => {
    for (const [markup, label] of [[ready(), corner.label], [stage('ta', { kind: 'listening', qid: 'q1' }), corner.label], [failed(), hold.label]] as const) {
      assert.equal((markup.match(/ data-phase="/g) ?? []).length, 1)
      assert.ok(labels(markup).includes(label))
      assert.ok(icons(markup).includes('lock'))
    }
  })

  it('is icon-only on Start and in the session: 48 x 48, its label is a screen-reader name and a tooltip, and no text shows until it is held', () => {
    for (const markup of [ready(), stage('hi', { kind: 'speaking', segment: 'instruction' })]) {
      assert.match(markup, new RegExp(`<span class="sr-only">${corner.label}</span>`), 'the name is screen-reader text')
      assert.match(markup, new RegExp(`title="${corner.label}"`), 'and a tooltip')
      assert.match(markup, /class="held-label hidden whitespace-nowrap"/, 'the short label is there, hidden, for the moment it is held')
      assert.match(unescape(markup), /\[&>button\]:size-12/, 'a 48 x 48 button')
      assert.match(unescape(markup), /\[&>button\]:border-transparent/, 'with no border while idle')
      assert.ok(!/aria-label=/.test(buttons(markup).find((b) => b.attrs.includes('data-phase'))?.attrs ?? ''))
    }
  })

  it('shows its short supervisor-language label only while it is held (the visible text is the holding label, hidden until then)', () => {
    const markup = stage('ta', { kind: 'listening', qid: 'q1' })
    assert.match(unescape(markup), /\[&>button:not\(\[data-phase=idle\]\)_\.held-label\]:inline/)
    assert.ok(visibleText(markup).includes(corner.holdingLabel))
  })

  it('spells every variant class of the corner lock out in full in the source (Tailwind only generates a class it can read whole)', () => {
    const src = readFileSync(new URL('../../src/screens/brief/WorkerScreens.tsx', import.meta.url), 'utf8')
    assert.doesNotMatch(src, /`[^`]*\$\{[^}]*\}[^`]*\[&>/, 'no class built from a template string')
    for (const cls of ['[&>button]:size-12', '[&>button:not([data-phase=idle])]:w-auto', '[&>button:not([data-phase=idle])_.held-label]:inline']) assert.ok(src.includes(cls), cls)
  })

  it('keeps its text on the failure screen: there the supervisor has to find it at once', () => {
    const markup = failed()
    assert.doesNotMatch(markup, /held-label|size-12/)
    assert.ok(labels(markup).includes(hold.label))
  })

  it('is not a plain button: pressing it needs the hold, so a worker cannot end the round by a tap', () => {
    const markup = stage('hi', { kind: 'speaking', segment: 'instruction' })
    const held = buttons(markup).find((b) => b.text.includes(corner.label))
    assert.ok(held, 'the held button is there')
    assert.match(held.attrs, /data-phase="idle"/)
    assert.match(held.attrs, /aria-describedby=/)
  })

  it('needs 1.5 seconds of holding (the fill that counts it down is set to 1500 ms)', () => {
    for (const markup of [stage('ta', { kind: 'listening', qid: 'q1' }), ready(), failed(), handBack()]) assert.match(markup, /--hold-ms:1500ms/)
  })

  it('on the hand-back it is "Supervisor: hold to continue", held and not tapped: a worker who taps it opens nothing', () => {
    const markup = handBack('hi')
    const takes = buttons(markup).filter((b) => b.text === HOLD_TO_CONTINUE)
    assert.equal(takes.length, 1, 'exactly one such control')
    assert.match(takes[0]?.attrs ?? '', /data-phase="idle"/)
    assert.equal((markup.match(/ data-phase="/g) ?? []).length, 1, 'the only held button on the hand-back screen')
  })

  it('on the hand-back it is the quiet control: outlined, default 48 px, below the worker’s red problem button', () => {
    const markup = handBack('ta')
    const all = buttons(markup)
    const problem = all.findIndex((b) => b.attrs.includes('bg-error'))
    const continueAt = all.findIndex((b) => b.text === HOLD_TO_CONTINUE)
    assert.ok(problem >= 0 && continueAt > problem, 'it comes after the problem button')
    const attrs = all[continueAt]?.attrs ?? ''
    assert.match(attrs, /min-h-12/, 'default size')
    assert.doesNotMatch(attrs, /min-h-16|bg-primary/, 'not the 64 px ink primary')
    assert.match(attrs, /border-\[1\.5px\] border-outline/, 'outlined')
    assert.match(unescape(markup), /\[&>button\]:w-full/, 'across the width of the screen')
    assert.ok(!markup.includes('border-t'), 'no separate bottom bar for it')
    assert.ok(icons(markup).includes('lock'))
  })

  it('on the hand-back it stays operable without a pointer: its hint is its description, and assistive technology gets a confirm dialog', () => {
    const markup = handBack('ta')
    const takes = buttons(markup).find((b) => b.text === HOLD_TO_CONTINUE)
    assert.match(takes?.attrs ?? '', /aria-describedby=/)
    assert.match(markup, /<dialog[^>]*>/)
    assert.ok(visibleText(markup).includes(haveHold.confirm.title))
    assert.ok(labels(markup).includes(haveHold.confirm.confirmLabel))
  })
})

// Compassion pass (16 Oct, build-notes/32): the worker is told, in their own language, what happens next and that this is not a
// test of them (product rule 3), and is thanked before giving the phone back. Worker-language text only, so F2 still holds.
describe('the worker screens are kind, in the worker’s own language', () => {
  for (const lang of LANGS) {
    const w = WORKER_WORDS[lang]

    it(`${lang}: Start says what happens next and that it is not a test, above the one Start button`, () => {
      const markup = html(createElement(WorkerReady, { ...where(lang), hold: corner, report, onStart: () => undefined }))
      const text = workerText(markup)
      assert.ok(text.includes(w.readyHow), `${lang}: ${text}`)
      assert.ok(text.includes(w.readyKind), `${lang}: ${text}`)
      // lastIndexOf: the screen-reader heading at the top also says Start; the button is the last one.
      assert.ok(text.indexOf(w.readyKind) < text.lastIndexOf(w.start), `${lang}: the reassurance comes before the Start button`)
    })

    it(`${lang}: the hand-back thanks the worker before it asks for the phone`, () => {
      const text = workerText(html(createElement(WorkerHandBack, { ...where(lang), report, haveThePhone: haveHold })))
      assert.ok(text.includes(w.thanks), `${lang}: ${text}`)
      assert.ok(text.indexOf(w.thanks) < text.indexOf(w.handBack), `${lang}: thanks first`)
    })

    it(`${lang}: the kind words are written in the worker's language, never in English`, () => {
      for (const s of [w.readyHow, w.readyKind, w.thanks]) {
        assert.ok(s.trim().length > 0)
        if (lang !== 'en') assert.doesNotMatch(s, /[A-Za-z]{2,}/, `${lang}: ${s}`)
      }
    })
  }
})
