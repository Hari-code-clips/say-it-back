import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { after, before, describe, it } from 'node:test'
import type { Lang } from '../../src/api/types.ts'
import { LANG_NAMES } from '../../src/i18n/langNames.ts'
import { WORKER_WORDS } from '../../src/i18n/worker.ts'
import { publicCatalog } from '../../src/mock/catalog.ts'
import { closingFor, NEUTRAL_THANKS } from '../../src/mock/script.ts'
import * as store from '../../src/mock/store.ts'
import { HttpError } from '../../src/mock/util.ts'

// 17 Oct (build-notes/37-telugu-consent.md): Telugu (`te`) is a worker language of the Chennai site, and the worker's consent screen
// says in every worker language that the voice goes to Google's computers outside the country (outside review P0-14).
// Every Telugu string and every new consent line is a machine draft pending native review.

const globals = ['window', 'localStorage'] as const
const saved = globals.map((name) => Object.getOwnPropertyDescriptor(globalThis, name))
before(() => {
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { location: { origin: 'http://localhost' } } })
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: () => null } })
})
after(() => {
  globals.forEach((name, i) => {
    const descriptor = saved[i]
    if (descriptor) Object.defineProperty(globalThis, name, descriptor)
    else Reflect.deleteProperty(globalThis, name)
  })
})

const read = (path: string) => readFileSync(new URL(`../../${path}`, import.meta.url), 'utf8')
const TELUGU = /^[ఀ-౿‌\s0-9.,?!…]+$/u // Telugu letters, ZWNJ (సూపర్‌వైజర్), digits and punctuation

describe('Telugu on the worker’s screen', () => {
  const te = WORKER_WORDS.te

  it('has every worker word, each non-empty and written in Telugu only', () => {
    assert.deepEqual(Object.keys(te).sort(), Object.keys(WORKER_WORDS.en).sort())
    for (const [key, text] of Object.entries(te)) {
      assert.ok(text.trim().length > 0, key)
      assert.match(text, TELUGU, `${key}: ${text}`)
    }
  })

  it('keeps rule 2: never "understood", "approved" or "passed"', () => {
    // అర్థమై… (understood), ఆమోద… (approval), ఉత్తీర్ణ… (passed an exam), పాస్ (pass)
    const banned = /అర్థమై|ఆమోద|ఉత్తీర్ణ|పాస్/u
    assert.deepEqual(Object.entries(te).filter(([, text]) => banned.test(text)), [])
  })

  it('keeps both consent buttons to one short line at 320 px', () => {
    for (const label of [te.consentAgree, te.consentNotNow]) assert.ok(label.length <= 16, label)
  })

  it('is marked DRAFT for native review', () => {
    assert.match(read('src/i18n/worker.ts'), /every Telugu word \(`te`[\s\S]{0,400}NEED NATIVE-SPEAKER REVIEW/)
  })

  it('is named in each UI language', () => {
    assert.deepEqual([LANG_NAMES.en.te, LANG_NAMES.ta.te, LANG_NAMES.zh.te], ['Telugu', 'தெலுங்கு', '泰卢固语'])
  })

  it('loads Noto Sans Telugu like the other scripts (the same lazy stylesheet, so the CSP is unchanged)', () => {
    assert.match(read('vite.config.ts'), /const NOTO_SCRIPTS = \[[^\]]*'Telugu'[^\]]*\]/)
    assert.match(read('src/styles/index.css'), /--font-sans:[^;]*"Noto Sans Telugu"/)
  })
})

describe('Telugu in the catalog and the mock', () => {
  it('the mock catalog is a byte copy of the backend catalog', () => {
    assert.equal(read('src/mock/catalog.json'), read('../backend/sayitback/data/catalog.json'))
  })

  it('Chennai offers Telugu to workers; Singapore does not', () => {
    const catalog = publicCatalog
    const site = (id: string) => catalog.sites.find((s) => s.id === id)
    assert.ok(site('chennai')?.workerLanguages.includes('te'))
    assert.ok(!site('sg')?.workerLanguages.includes('te'))
    assert.equal(catalog.languages.te.native, 'తెలుగు')
    assert.equal(catalog.languages.te.bcp47, 'te-IN')
  })

  it('the mock briefs a Telugu worker in Chennai, closes in Telugu, and refuses Telugu in Singapore', () => {
    const b = store.createBriefing({ siteId: 'chennai', taskId: 'trench-entry', supervisorLang: 'ta', workerLang: 'te', instruction: 'Use only the ladder.' })
    assert.equal(b.workerLang, 'te')
    assert.match(closingFor(b), TELUGU)
    assert.match(NEUTRAL_THANKS.te ?? '', TELUGU)
    assert.throws(
      () => store.createBriefing({ siteId: 'sg', taskId: 'lifting-zone', supervisorLang: 'en', workerLang: 'te', instruction: 'Never go under the load.' }),
      (e: unknown) => e instanceof HttpError && e.code === 'unsupported_language',
    )
  })
})

// What each language's consent line must hold: Google, outside the country, and deleted within a day.
const DISCLOSURE: Record<Lang, [google: string, outside: string, withinADay: string]> = {
  en: ["Google's computers", 'outside this country', 'It is deleted after the check, within a day.'],
  zh: ['谷歌', '这个国家以外', '最多保留一天'],
  ta: ['கூகுள்', 'நாட்டுக்கு வெளியே', 'ஒரு நாளுக்குள்'],
  bn: ['গুগল', 'দেশের বাইরে', 'এক দিনের মধ্যে'],
  my: ['ဂူဂဲလ်', 'နိုင်ငံပြင်ပ', 'တစ်ရက်အတွင်း'],
  hi: ['गूगल', 'देश के बाहर', 'एक दिन के अंदर'],
  or: ['ଗୁଗଲ', 'ଦେଶ ବାହାରେ', 'ଏକ ଦିନ ଭିତରେ'],
  te: ['గూగుల్', 'దేశం బయట', 'ఒక రోజులోపు'],
}

describe('the consent screen says where the voice goes (outside review P0-14)', () => {
  it('covers all eight worker languages', () => {
    assert.deepEqual(Object.keys(DISCLOSURE).sort(), Object.keys(WORKER_WORDS).sort())
    assert.equal(Object.keys(WORKER_WORDS).length, 8)
  })

  for (const [lang, parts] of Object.entries(DISCLOSURE) as [Lang, string[]][]) {
    it(`${lang}: Google, outside the country, only for this check, deleted within a day`, () => {
      const line = WORKER_WORDS[lang].consentUse
      for (const part of parts) assert.ok(line.includes(part), `${lang}: "${part}" is not in "${line}"`)
      if (lang !== 'en') assert.doesNotMatch(line, /[A-Za-z]/, `${lang}: Latin letters on the worker's screen: ${line}`)
    })
  }

  it('says, in English, that the voice is used only to check this briefing', () => {
    assert.match(WORKER_WORDS.en.consentUse, /^Your voice goes to Google's computers outside this country, only to check this briefing\./)
  })

  it('the new lines are marked DRAFT for native review', () => {
    assert.match(read('src/i18n/worker.ts'), /disclosure added\n\/\/ to `consentUse` in every language[\s\S]{0,300}NEED NATIVE-SPEAKER REVIEW/)
  })
})
