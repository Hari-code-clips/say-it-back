import assert from 'node:assert/strict'
import { after, describe, it } from 'node:test'
import type { ComponentType, ReactElement } from 'react'
import { Router } from 'wouter'
import type { Briefing } from '../../src/api/types.ts'
import * as store from '../../src/mock/store.ts'
import type { SampleChoice } from '../../src/screens/brief/sample.ts'
import { buttons, createElement, html, icons, startSsr, visibleText, withUiLang } from '../helpers/ssr.ts'

// F1 and F3 on the supervisor's side: the script screen (approve, English first, the worker's text second and collapsed), the
// handover step (mode, stored sample answers, "Give phone to worker"), and the check's wait (three stages, static, with a bound).

type Props = Record<string, unknown>
const ssr = await startSsr()
after(() => ssr.close())
const { I18nProvider } = await ssr.load<{ I18nProvider: ComponentType<Props> }>('/src/i18n/index.tsx')
const { CatalogProvider } = await ssr.load<{ CatalogProvider: ComponentType<Props> }>('/src/api/catalog.tsx')
const { FeedbackProvider } = await ssr.load<{ FeedbackProvider: ComponentType<Props> }>('/src/ui/FeedbackProvider.tsx')
const { BriefingContext } = await ssr.load<{ BriefingContext: ComponentType<Props> }>('/src/flow/BriefingContext.tsx')
const { ScriptScreen } = await ssr.load<{ ScriptScreen: ComponentType }>('/src/screens/ScriptScreen.tsx')
const { BriefScreen } = await ssr.load<{ BriefScreen: ComponentType }>('/src/screens/brief/BriefScreen.tsx')
const { HandoverForm } = await ssr.load<{ HandoverForm: ComponentType<Props> }>('/src/screens/brief/HandoverForm.tsx')
const { CheckWait } = await ssr.load<{ CheckWait: ComponentType<Props> }>('/src/screens/brief/CheckWait.tsx')

/** A real round from the mock backend: the lead demo, English supervisor, Tamil worker. */
function leadBriefing(approved: boolean): Briefing {
  const b = store.createBriefing({
    siteId: 'sg', taskId: 'lifting-zone', supervisorLang: 'en', workerLang: 'ta',
    instruction: "Never go under the load, stay outside the barrier until it's landed, and only follow the signalman.",
  })
  store.confirmSteps(b.id, store.extractSteps(b.id).steps)
  store.createRound(b.id, {})
  if (approved) store.approveRound(b.id, 1)
  return store.getBriefing(b.id)
}

function screen(briefing: Briefing, path: string, node: ReactElement, lang: 'en' | 'ta' | 'zh' = 'en'): string {
  const value = { briefing, setBriefing: () => undefined, refresh: async () => briefing }
  return withUiLang(lang, () =>
    html(
      createElement(Router, {
        ssrPath: `/b/${briefing.id}/${path}`,
        children: createElement(I18nProvider, null, createElement(CatalogProvider, null, createElement(FeedbackProvider, null, createElement(BriefingContext, { value }, node)))),
      }),
    ),
  )
}

/** The language pair in the context line ("English → தமிழ்") names the language in its own script: that Tamil is a label, not the script. */
const withoutLanguageName = (markup: string): string => markup.replaceAll('தமிழ்', '')

const unapproved = leadBriefing(false)
const approvedBriefing = leadBriefing(true)

describe('F1: the script screen is act one, approval', () => {
  const markup = screen(unapproved, 'script', createElement(ScriptScreen))
  const text = visibleText(markup)

  it('has one primary, "Approve script", and nothing that hands the phone over', () => {
    assert.ok(buttons(markup).some((b) => b.text === 'Approve script'))
    assert.ok(!text.includes('Give phone to worker'), 'the handover is the next screen')
    assert.ok(!text.includes('Hand phone to worker'), 'the old label is gone')
    assert.ok(!text.includes('Go to the handover'), 'not yet approved')
    assert.ok(!text.includes('Your approval was recorded'))
  })

  it('puts the English back-translation first, then the questions, then the closing line, then the worker’s text', () => {
    const at = (needle: string) => {
      const i = text.indexOf(needle)
      assert.ok(i >= 0, `"${needle}" is missing`)
      return i
    }
    const order = [at('What the worker will hear, in English'), at('Questions the worker will be asked'), at('Closing line'), at('Show the Tamil text')]
    assert.deepEqual(order, [...order].sort((a, b) => a - b))
  })

  it('reads the instruction back in English before it shows a word of Tamil', () => {
    const back = unapproved.rounds[0]?.script.instructionBackTranslation ?? ''
    assert.ok(back.length > 20)
    const bare = withoutLanguageName(markup)
    const backAt = bare.indexOf(back.slice(0, 20))
    const tamilAt = bare.search(/[\u0B80-\u0BFF]/)
    assert.ok(backAt >= 0 && tamilAt >= 0)
    assert.ok(backAt < tamilAt, 'the first Tamil letter comes before the English back-translation')
  })

  it('keeps the worker-language text in a disclosure that starts closed', () => {
    const details = markup.match(/<details\b[^>]*>/)
    assert.ok(details, 'a disclosure')
    assert.ok(!/\bopen\b/.test(details[0]), 'closed')
    const body = markup.slice(markup.indexOf('</summary>'))
    assert.match(body, /[\u0B80-\u0BFF]/, 'the Tamil is inside it')
    assert.doesNotMatch(withoutLanguageName(markup.slice(0, markup.indexOf('<details'))), /[\u0B80-\u0BFF]/, 'and nowhere before it')
  })

  it('says the closing line has no English translation, because the data carries none', () => {
    assert.ok(text.includes('There is no English translation of this line, so it cannot be checked here.'))
  })

  it('does not say "ticket" or "approved"', () => {
    assert.doesNotMatch(text, /ticket|approved/i)
  })
})

describe('F1: once approved, the script screen only moves on', () => {
  const markup = screen(approvedBriefing, 'script', createElement(ScriptScreen))
  const text = visibleText(markup)

  it('says when the approval was recorded and offers "Go to the handover", not a second approval', () => {
    assert.ok(text.includes('Your approval was recorded at'))
    assert.ok(buttons(markup).some((b) => b.text === 'Go to the handover'))
    assert.ok(!buttons(markup).some((b) => b.text === 'Approve script'))
  })
})

describe('F1: the handover step (act two), in the supervisor’s language', () => {
  const markup = screen(approvedBriefing, 'brief', createElement(BriefScreen))
  const text = visibleText(markup)

  it('opens as a supervisor screen: "Give phone to worker", the mode choice, and the sample choice moved here', () => {
    assert.ok(buttons(markup).some((b) => b.text === 'Give phone to worker'))
    assert.ok(text.includes('Live voice') && text.includes('Turn by turn'))
    assert.ok(text.includes('Use stored sample answers for this round'))
    assert.ok(!text.includes('Approve script'), 'approval is the previous screen')
  })

  it('shows no worker control yet: no Start, no problem button, no held "I’m the supervisor"', () => {
    assert.ok(!text.includes('தொடங்கு'))
    assert.ok(!text.includes('பிரச்சனை உள்ளது'))
    assert.ok(!markup.includes(' data-phase="'))
  })

  it('tells the supervisor how to stop the round once the worker has the phone', () => {
    assert.ok(text.includes('hold the lock button at the top of the worker'))
  })

  it('keeps the worker’s Tamil off the supervisor’s screen', () => {
    assert.doesNotMatch(withoutLanguageName(markup), /[\u0B80-\u0BFF]/)
  })

  it('is written in Tamil for a Tamil supervisor, with "Give phone to worker" as its primary', () => {
    const ta = screen(approvedBriefing, 'brief', createElement(BriefScreen), 'ta')
    assert.ok(buttons(ta).some((b) => b.text === 'தொழிலாளரிடம் கொடு'))
    assert.doesNotMatch(visibleText(ta), /Give phone|Live voice/)
  })
})

/** The sample checkbox's own tag (the mode radios on the same form are `checked` too). */
const checkbox = (markup: string): string => markup.match(/<input type="checkbox"[^>]*>/)?.[0] ?? ''

describe('F1: the sample choice says honestly which questions have a stored sample', () => {
  /** The choice for these question numbers (1-based) of the round; `all`: they are every question it has. */
  const choice = (numbers: number[] = [1], all = false, stepsLeft = false): SampleChoice => ({
    kind: 'available',
    pairs: numbers.map((n) => ({ qid: `q${n}`, item: { taskId: 't', workerLang: 'ta', round: 1, gloss: '', questionId: `q${n}`, stepIds: [] } })),
    numbers,
    all,
    stepsLeft,
  })
  const form = (sample: SampleChoice, sampleOn = false, lang: 'en' | 'ta' | 'zh' = 'en', workerName = 'Tamil') =>
    withUiLang(lang, () => html(createElement(I18nProvider, null, createElement(HandoverForm, { mode: 'live', onMode: () => undefined, sample, sampleOn, onSampleOn: () => undefined, workerName }))))

  it('says plainly when every question has one (16 Oct): nobody needs to speak the worker language, and it is still a synthetic voice', () => {
    for (const numbers of [[1, 2, 3], [1, 2]]) {
      const text = visibleText(form(choice(numbers, true)))
      assert.ok(text.includes('Every question has a stored sample answer. Nobody needs to speak Tamil. They are a synthetic voice, not the worker, and the result marks them as samples.'), text)
      assert.ok(!text.includes('other questions') && !text.includes('exist for'))
    }
  })

  it('says it in the singular for a round with one question', () => {
    const text = visibleText(form(choice([1], true)))
    assert.ok(text.includes('Every question has a stored sample answer. Nobody needs to speak Tamil. It is a synthetic voice, not the worker, and the result marks it as a sample.'))
  })

  it('names question 1, says it is a synthetic voice that the result marks, and that the others are by voice', () => {
    const text = visibleText(form(choice()))
    assert.ok(text.includes('A stored sample answer exists for question 1.'))
    assert.ok(text.includes('synthetic voice, not the worker'))
    assert.ok(text.includes('marks it as a sample'))
    assert.ok(text.includes('The worker answers the other questions by voice.'))
    assert.ok(!text.includes('Nobody needs to speak'))
  })

  it('names every question that has one when only some do', () => {
    const text = visibleText(form(choice([1, 3])))
    assert.ok(text.includes('Stored sample answers exist for questions 1 and 3. They are a synthetic voice'))
    assert.ok(text.includes('marks them as samples. The worker answers the other questions by voice.'))
  })

  it('when every question has one but a step is in none of them, says that step may need another round, not "every question"', () => {
    const text = visibleText(form(choice([1, 2], false, true)))
    assert.ok(text.includes('Stored sample answers exist for questions 1 and 2.'))
    assert.ok(text.includes('Some steps are in no stored answer, so they may need another round.'))
    assert.ok(!text.includes('Nobody needs to speak') && !text.includes('other questions by voice'))
  })

  it('says there is no stored sample for this task, language and round, and turns the choice off with that reason beside it', () => {
    const markup = form({ kind: 'none' }, true)
    assert.ok(visibleText(markup).includes('No stored sample answer exists for this task, language and round. The worker answers every question by voice.'))
    assert.match(checkbox(markup), /aria-disabled="true"/)
    assert.doesNotMatch(checkbox(markup), /checked/, 'a choice made earlier does not carry over to a round with no sample')
  })

  it('reads "looking" while the list loads', () => {
    assert.ok(visibleText(form({ kind: 'loading' })).includes('Looking for a stored sample answer'))
  })

  it('is ticked only when it is available and chosen', () => {
    assert.match(checkbox(form(choice(), true)), /checked/)
    assert.doesNotMatch(checkbox(form(choice(), false)), /checked/)
  })

  it('is written in Tamil and Chinese for those supervisors', () => {
    assert.match(visibleText(form(choice(), false, 'ta')), /கேள்வி 1/)
    assert.match(visibleText(form(choice(), false, 'zh')), /第 1 题/)
  })

  it('in Tamil and Chinese too, names the worker language in theirs when every question has one, and lists the questions', () => {
    assert.match(visibleText(form(choice([1, 2, 3], true), false, 'ta', 'தமிழ்')), /எல்லாக் கேள்விகளுக்கும் சேமித்த மாதிரிப் பதில் உள்ளது. யாரும் தமிழ் பேசத் தேவையில்லை. அவை செயற்கைக் குரல்/)
    assert.match(visibleText(form(choice([1, 2, 3], true), false, 'zh', '泰米尔语')), /每道题都有存储的示例回答。没有人需要说泰米尔语。它们是合成语音/)
    assert.match(visibleText(form(choice([1, 3]), false, 'ta')), /கேள்விகள் 1 மற்றும் 3-க்குச்/)
    assert.match(visibleText(form(choice([1, 3]), false, 'zh')), /第 1和3 题/)
  })
})

describe('F3: the check’s wait shows the three stages as a static list, the real elapsed time and the bound', () => {
  const wait = (ago: number, lang: 'en' | 'ta' | 'zh' = 'en') => withUiLang(lang, () => html(createElement(I18nProvider, null, createElement(CheckWait, { startedAt: Date.now() - ago }))))

  it('lists blind transcript, two judges, fixed rules, in that order', () => {
    const text = visibleText(wait(0))
    const at = ['written out as text, without the steps', 'Two independent judges', 'Fixed rules check the result'].map((s) => text.indexOf(s))
    assert.ok(at.every((i) => i >= 0), String(at))
    assert.deepEqual(at, [...at].sort((a, b) => a - b))
  })

  it('states the bound, "Usually 15–40 seconds"', () => {
    assert.ok(visibleText(wait(0)).includes('Usually 15–40 seconds.'))
  })

  it('does not pretend to know the stage: no ticks, no spinner per stage, one indeterminate bar, and it says so', () => {
    const markup = wait(30_000)
    assert.equal((markup.match(/role="progressbar"/g) ?? []).length, 1)
    for (const mark of ['check', 'check_circle', 'task_alt', 'done']) assert.ok(!icons(markup).includes(mark), mark)
    assert.ok(visibleText(markup).includes('The server does not say which of these is running.'))
    assert.doesNotMatch(markup, /aria-current|aria-valuenow/)
  })

  it('counts the time from when the check went out, not from when the supervisor took the phone', () => {
    assert.ok(visibleText(wait(65_000)).includes('1:05 elapsed'))
  })

  it('says it is still working from 45 s', () => {
    assert.ok(!visibleText(wait(20_000)).includes('Still working'))
    assert.ok(visibleText(wait(50_000)).includes('Still working'))
  })

  it('is written in Tamil and Chinese too, with the same bound', () => {
    assert.ok(visibleText(wait(0, 'ta')).includes('வழக்கமாக 15–40 வினாடிகள் ஆகும்.'))
    assert.ok(visibleText(wait(0, 'zh')).includes('通常需要 15–40 秒。'))
  })
})
