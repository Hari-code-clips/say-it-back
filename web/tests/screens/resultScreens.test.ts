import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import { askedAbout, disagreementHint } from '../../src/screens/result/verdict.ts'

// F4-F6 (build-notes/25) at the level this suite can reach: the pure helpers, and the shape of the screens that use them. The React
// tree is not rendered here (node:test, no DOM), so the structure checks read the source; each was broken once to prove it fails.

const source = (path: string) => readFileSync(new URL(`../../src/screens/${path}`, import.meta.url), 'utf8')

describe('what to do when the judges disagree (F4)', () => {
  const flags = ['passes_disagreed']

  it('Ask again: listen, then re-explain or check in person', () => {
    const key = disagreementHint('unclear', flags)
    assert.equal(key, 'result.disagreedAsk')
    assert.match(en[key!], /Ask again/)
    assert.match(en[key!], /re-explain/i)
  })

  it('Wrong (a contradiction in either judge stands): listen before deciding', () => {
    const key = disagreementHint('contradicted', flags)
    assert.equal(key, 'result.disagreedWrong')
    assert.match(en[key!], /reads Wrong/)
  })

  it('says nothing without the flag, and nothing false for a record from before v0.5.3', () => {
    assert.equal(disagreementHint('unclear', []), null)
    assert.equal(disagreementHint('contradicted', ['low_confidence']), null)
    // Before v0.5.3 the more severe verdict won, so a split could be Missed; it must not be told "reads Ask again".
    assert.equal(disagreementHint('missed', flags), null)
    assert.equal(disagreementHint('covered', flags), null)
  })

  it('the sentences are in all three languages', () => {
    for (const key of ['result.disagreedAsk', 'result.disagreedWrong'] as const) for (const table of [en, ta, zh]) assert.match(table[key], /\S/)
  })
})

describe('the worker audio beside the verdict (F4)', () => {
  const questions = [
    { id: 'q1', stepIds: ['s1', 's2'] },
    { id: 'q2', stepIds: ['s3'] },
    { id: 'q3', stepIds: ['s1'] },
  ]

  it('lists the answers that check a step, with their number in the round', () => {
    assert.deepEqual(askedAbout(questions, 's1').map((a) => [a.question.id, a.number]), [['q1', 1], ['q3', 3]])
    assert.deepEqual(askedAbout(questions, 's3').map((a) => a.number), [2])
  })

  it('is empty for a step no question asked about', () => {
    assert.deepEqual(askedAbout(questions, 's9'), [])
  })

  it('both the at-a-glance row and the step card draw the clip player from it', () => {
    assert.match(source('result/GlanceList.tsx'), /askedAbout\([^)]*\)[\s\S]*<ClipPlayer/)
    assert.match(source('result/ResultScreen.tsx'), /asked=\{askedAbout\(/)
    assert.match(source('result/StepResultCard.tsx'), /<ClipPlayer/)
  })
})

describe('the result screen (F4)', () => {
  const screen = source('result/ResultScreen.tsx')

  it('puts Re-explain and Decide in the sticky bar, not in the page', () => {
    assert.match(screen, /primary=\{action\(bar\.primary, true\)\}/)
    assert.match(screen, /secondary=\{bar\.secondary \? action\(bar\.secondary, false\) : undefined\}/)
    // Both buttons are made by `action` and nowhere else on the screen.
    assert.equal((screen.match(/t\('result\.reexplain'\)/g) ?? []).length, 1)
    assert.equal((screen.match(/t\('result\.decide'\)/g) ?? []).length, 1)
    assert.ok(!/result\.decideNow/.test(screen))
  })

  it('makes the secondary default size (48 px), the primary large', () => {
    // Both actions are built with the same rule, so whichever of them is the secondary is 48 px.
    assert.equal((screen.match(/size=\{primary \? 'lg' : 'md'\}/g) ?? []).length, 2)
  })

  it('orders the page: the report banner, At a glance, then the details (the step cards)', () => {
    const at = (needle: string) => screen.indexOf(needle)
    assert.ok(at('<HazardBanner') >= 0 && at('<HazardBanner') < at('id="result-glance"'))
    assert.ok(at('id="result-glance"') < at('<HazardSection'))
    assert.ok(at('<HazardSection') < at('<StepResultCard'))
  })

  it('a reported problem is one compact banner that jumps to the note, not a form on top', () => {
    const hazard = source('hazard/HazardSection.tsx')
    assert.match(hazard, /export function HazardBanner/)
    assert.match(hazard, /onClick=\{jumpToHazardNote\}/)
    assert.equal(en['hazard.banner'], 'Worker reported a problem · Go is locked until you note what you did')
    assert.match(en['hazard.bannerMany'], /\{n\} problems/)
  })

  it('has no side stripe, no uppercase caption and no card-in-card tint on the screens of this build', () => {
    for (const file of ['hazard/HazardSection.tsx', 'result/StepResultCard.tsx', 'result/DeliverySection.tsx', 'result/AnswersSection.tsx', 'result/SampleTag.tsx', 'StepsScreen.tsx', 'steps/StepCard.tsx', 'RecordScreen.tsx', 'record/ChainPanel.tsx']) {
      const text = source(file)
      assert.ok(!/border-(l|r)-\d/.test(text), `${file}: no side stripe`)
      assert.ok(!/\buppercase\b|tracking-wide/.test(text.replace(/\/\*[\s\S]*?\*\//g, '')), `${file}: no uppercase caption`)
    }
  })
})

describe('the decision screen (F5)', () => {
  const screen = source('DecisionScreen.tsx')

  it('Record decision only opens the confirm; the request is sent from the dialog', () => {
    assert.match(screen, /onClick=\{\(\) => setConfirming\(true\)\}/)
    // In the markup (after the component's `return`), the only call of submit() is the dialog's own button.
    const markup = screen.slice(screen.indexOf('<FlowFrame'))
    const uses = [...markup.matchAll(/void submit\(\)/g)].map((m) => m.index ?? 0)
    assert.equal(uses.length, 1)
    assert.ok(markup.indexOf('<Dialog') < uses[0]!, 'and it is inside the dialog')
  })

  it('shows why the button is off, through disabledReason', () => {
    assert.match(screen, /disabledReason=\{gate\.reasonKey \? t\(gate\.reasonKey\) : undefined\}/)
  })

  it('Go and No-go come first, then the compact report banner, the reason, then the evidence', () => {
    const at = (needle: string) => screen.indexOf(needle)
    assert.ok(at('name="decision"') >= 0 && at('name="decision"') < at('<HazardBanner'), 'the choices come before the banner')
    assert.ok(at('<HazardBanner') < at("label={needReason ?"), 'the banner is under the choices, above the reason')
    assert.ok(at("label={needReason ?") < at('<HazardSection'))
    assert.ok(at('<HazardSection') < at("id=\"decision-checked\""))
  })

  it('the choices are the compact 72 px cards, so both are above the bar at 375 x 667 with a problem or open steps (browser-checked)', () => {
    assert.ok(!/RadioCard/.test(screen), 'RadioCard is 96 px or more per choice')
    assert.equal((screen.match(/<DecisionChoice\b/g) ?? []).length, 2)
    assert.match(source('result/DecisionChoice.tsx'), /min-h-\[4\.5rem\]/)
    // The Go lock reason is short enough for two lines on a phone: the same sentence is in the banner below.
    assert.ok(en['decision.goLocked'].length <= 70)
  })

  it('keeps the Go lock for an open reported problem', () => {
    assert.match(screen, /disabled=\{goLocked\}/)
    assert.match(screen, /checked=\{choice === 'go' && !goLocked\}/)
  })

  it('closes the dialog when the request fails, so the error is not hidden behind it', () => {
    assert.match(screen, /setBusy\(false\)\s*\n\s*setConfirming\(false\)/)
  })
})

describe('the re-explain screen (F6)', () => {
  const screen = source('ReexplainScreen.tsx')

  it('the primary is "Write the re-explanation", with a reason when it is off', () => {
    assert.equal(en['reexplain.write'], 'Write the re-explanation')
    assert.match(screen, /disabledReason=\{valid \? undefined : t\('reexplain\.need'\)\}/)
  })

  it('both choices come before the open steps, and the wait takes the choices\' place at the top', () => {
    assert.ok(screen.indexOf('name="method"') < screen.indexOf('id="reexplain-open"'))
    assert.match(screen, /\{busy \? \(\s*<WaitInView/)
  })
})

describe('the waits that were behind the bar (note 25, "Also")', () => {
  it('Instruction, Steps and Re-explain use WaitInView, which scrolls the panel into view', () => {
    for (const file of ['InstructionScreen.tsx', 'StepsScreen.tsx', 'ReexplainScreen.tsx']) assert.match(source(file), /<WaitInView/, file)
    assert.match(source('instruction/WaitInView.tsx'), /scrollIntoView/)
    // The old position, below the controls, is gone.
    assert.ok(!/<BusyPanel/.test(source('InstructionScreen.tsx')))
    assert.ok(!/<BusyPanel/.test(source('StepsScreen.tsx')))
  })

  it('the Instruction wait comes before the form, so it is on screen at 320-414 px', () => {
    const screen = source('InstructionScreen.tsx')
    assert.ok(screen.indexOf('<WaitInView') < screen.indexOf('<fieldset'))
  })
})

// 16 Oct: with every question of a demo round answerable by a stored sample, a sample's words must never be captioned as the
// worker's, on any verdict (the quote's own transcript decides: lib/sampleCovered.ts quoteFromSample).
describe('a stored sample answer is never captioned "The worker said"', () => {
  it('the step card picks the sample caption when the quote is the sample’s, and the result screen tells it so', () => {
    assert.match(source('result/StepResultCard.tsx'), /quoteBySample \? 'result\.sampleSaid' : 'result\.workerSaid'/)
    assert.match(source('result/ResultScreen.tsx'), /quoteBySample=\{quoteFromSample\(round, s\.id,/)
  })

  it('says so in all three languages, without the worker in it', () => {
    for (const table of [en, ta, zh]) assert.match(table['result.sampleSaid'], /\{lang\}/)
    assert.doesNotMatch(en['result.sampleSaid'], /worker/i)
  })
})

describe('the decision says, at the reason field, why stored sample answers leave steps open', () => {
  it('uses the sample hint when any step is open only because of a sample', () => {
    assert.match(source('DecisionScreen.tsx'), /bySample\.size > 0 \? 'decision\.reasonHintSample' : 'decision\.reasonHint'/)
    for (const table of [en, ta, zh]) assert.match(table['decision.reasonHintSample'], /\{min\}/)
    assert.match(en['decision.reasonHintSample'], /stored sample answer/)
  })
})
