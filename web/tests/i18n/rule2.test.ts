import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import { WORKER_WORDS } from '../../src/i18n/worker.ts'
import { siteContext, siteName, taskTitle } from '../../src/i18n/catalogText.ts'
import type { Catalog } from '../../src/api/types.ts'
import catalogJson from '../../src/mock/catalog.json' with { type: 'json' }

const catalog = catalogJson as unknown as Catalog

// Product rule 2 (PROJECT_CONTEXT.md): the AI never approves work, so the UI never says "approved", "passed" or "understood",
// in any language. A covered step is "said back" (Chinese 已说到), never "understood" (Tamil புரிந்த).

const BANNED: Record<'en' | 'ta' | 'zh', RegExp> = {
  en: /\b(approved|passed|understood)\b/i,
  // "understood" (புரிந்த: it also catches புரிந்து, to understand, and புரிந்ததா, did they understand?); "approved" or
  // "recognised" (அங்கீகரி…), "approval" (ஒப்புதல்); "passed", as an exam is (தேர்ச்சி).
  ta: /புரிந்த|அங்கீகரி|ஒப்புதல்|தேர்ச்சி/u,
  // understood (理解, 明白), passed (通过), approved (批准, 审批), qualified as passing (合格)
  zh: /理解|明白|通过|批准|审批|合格/u,
}

/**
 * The only allowed exceptions. Each is about the evaluation's pass bar, a property of the checker's test results, never about a
 * worker or a piece of work, and is shown only on the Eval page.
 */
const PASS_BAR = ['eval.passMet', 'eval.passNotMet', 'eval.passBar', 'eval.passBarCorrect']
const EXCEPTIONS: Record<'en' | 'ta' | 'zh', ReadonlySet<string>> = {
  en: new Set(),
  ta: new Set(PASS_BAR), // தேர்ச்சி வரம்பு = "pass bar" (the checker's accuracy target)
  zh: new Set(PASS_BAR), // 通过线 = "pass bar" (the checker's accuracy target)
}

/** Every string the UI can show in a language: its table, the worker-screen words and the catalog text it fills in. */
function strings(lang: 'en' | 'ta' | 'zh'): [string, string][] {
  const table = { en, ta, zh }[lang] as Record<string, string>
  return [
    ...Object.entries(table),
    ...Object.entries(WORKER_WORDS[lang]).map(([k, v]): [string, string] => [`worker.${k}`, v]),
    ...catalog.sites.flatMap((site): [string, string][] => [
      [`site.${site.id}.name`, siteName(site, lang)],
      [`site.${site.id}.context`, siteContext(site, lang)],
    ]),
    ...catalog.tasks.map((task): [string, string] => [`task.${task.id}.title`, taskTitle(task, lang)]),
  ]
}

describe('rule 2 in every UI language: no "approved", "passed" or "understood"', () => {
  for (const lang of ['en', 'ta', 'zh'] as const) {
    it(`${lang}: no banned word outside the pass-bar exceptions`, () => {
      const offenders = strings(lang).filter(([key, text]) => BANNED[lang].test(text) && !EXCEPTIONS[lang].has(key))
      assert.deepEqual(offenders.map(([key, text]) => `${key}: ${text}`), [])
    })

    it(`${lang}: every exception still exists (a stale entry could hide a new string under its name)`, () => {
      const keys = new Set(strings(lang).map(([k]) => k))
      assert.deepEqual([...EXCEPTIONS[lang]].filter((k) => !keys.has(k)), [])
    })
  }

  it('catches the Tamil and Chinese words for approved and passed, not only understood', () => {
    for (const word of ['அங்கீகரிக்கப்பட்டது', 'ஒப்புதல் பெற்றது', 'தேர்ச்சி பெற்றார்', 'புரிந்துகொண்டார்']) assert.match(word, BANNED.ta, word)
    for (const word of ['已批准', '审批完成', '合格', '已通过', '已理解']) assert.match(word, BANNED.zh, word)
  })

  it('a covered step reads as said back in Tamil and Chinese', () => {
    assert.equal(zh['verdict.covered'], '已说到')
    assert.ok(!BANNED.ta.test(ta['verdict.covered']))
  })
})
