import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { after, afterEach, beforeEach, describe, it } from 'node:test'
import type { ComponentType } from 'react'
import { Router } from 'wouter'
import type { Catalog, CreateBriefingBody } from '../../src/api/types.ts'
import { JUDGE_DEMO_TASK, isJudgeDemo, judgeDemoBody, markJudgeDemo, startJudgeDemo } from '../../src/flow/judgeDemo.ts'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import catalog from '../../src/mock/catalog.json' with { type: 'json' }
import { buttons, createElement, html, startSsr, visibleText, withUiLang } from '../helpers/ssr.ts'

// 17 Oct, review P0-17 (build-notes/37-review-remainder.md): "Run the 90-second judge demo" on the landing page starts the lead case
// (Singapore, crane lift, English to Tamil, the sample instruction) and the handover opens with the stored sample answers chosen.

const CATALOG = catalog as unknown as Catalog
const lead = CATALOG.tasks.find((t) => t.id === 'lifting-zone')

/** A sessionStorage for node, or one whose every call throws (storage switched off). */
function useStorage(kind: 'map' | 'throws') {
  const had = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage')
  const items = new Map<string, string>()
  const boom = () => {
    throw new Error('storage is off')
  }
  const value =
    kind === 'map'
      ? { getItem: (k: string) => items.get(k) ?? null, setItem: (k: string, v: string) => void items.set(k, v), removeItem: (k: string) => void items.delete(k) }
      : { getItem: boom, setItem: boom, removeItem: boom }
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value })
  return () => {
    if (had) Object.defineProperty(globalThis, 'sessionStorage', had)
    else delete (globalThis as { sessionStorage?: unknown }).sessionStorage
  }
}

describe('the judge demo starts the lead case', () => {
  it('Singapore, Crane lift: the lifting zone, English to Tamil, with the catalogue sample instruction, and nothing else', () => {
    assert.equal(JUDGE_DEMO_TASK, 'lifting-zone')
    assert.equal(lead?.title.en, 'Crane lift: the lifting zone')
    assert.deepEqual(judgeDemoBody(CATALOG), {
      siteId: 'sg',
      taskId: 'lifting-zone',
      supervisorLang: 'en',
      workerLang: 'ta',
      instruction: lead?.sampleInstruction.en,
    })
  })

  it('finds the lead by its id, wherever the catalogue lists it', () => {
    const c = structuredClone(CATALOG)
    c.tasks.reverse()
    assert.notEqual(c.tasks[0]?.id, 'lifting-zone')
    assert.deepEqual(judgeDemoBody(c), judgeDemoBody(CATALOG))
  })

  it('is null without the lead task, with a pair its site does not offer, or with no sample instruction', () => {
    const none = structuredClone(CATALOG)
    none.tasks = none.tasks.filter((t) => t.id !== 'lifting-zone')
    assert.equal(judgeDemoBody(none), null)

    const pair = structuredClone(CATALOG)
    pair.tasks.find((t) => t.id === 'lifting-zone')!.demoPair = { supervisorLang: 'en', workerLang: 'hi' }
    assert.equal(judgeDemoBody(pair), null)

    const empty = structuredClone(CATALOG)
    empty.tasks.find((t) => t.id === 'lifting-zone')!.sampleInstruction = { en: '  ' }
    assert.equal(judgeDemoBody(empty), null)
  })
})

describe('startJudgeDemo', () => {
  let restore: () => void
  beforeEach(() => (restore = useStorage('map')))
  afterEach(() => restore())

  const body = judgeDemoBody(CATALOG) as CreateBriefingBody
  const fakeIo = (failExtracts = 0) => {
    const calls: string[] = []
    let failures = failExtracts
    return {
      calls,
      io: {
        create: async (b: CreateBriefingBody) => (calls.push(`create ${b.taskId} ${b.instruction}`), { id: 'b_judge1' }),
        patch: async (id: string, instruction: string) => calls.push(`patch ${id} ${instruction}`),
        extract: async (id: string) => {
          calls.push(`extract ${id}`)
          if (failures-- > 0) throw new Error('upstream_busy')
        },
      },
    }
  }

  it('creates the briefing once, marks it as the judge demo, finds the steps and opens the Steps screen', async () => {
    const { calls, io } = fakeIo()

    const path = await startJudgeDemo(body, { id: null }, io)

    assert.equal(path, '/b/b_judge1/steps')
    assert.deepEqual(calls, [`create lifting-zone ${body.instruction}`, 'extract b_judge1'])
    assert.equal(isJudgeDemo('b_judge1'), true)
    assert.equal(isJudgeDemo('b_other'), false)
  })

  it('after a failed extract, Retry finds the steps of the same briefing and creates no second one', async () => {
    const { calls, io } = fakeIo(1)
    const held = { id: null as string | null }

    await assert.rejects(startJudgeDemo(body, held, io), /upstream_busy/)
    assert.equal(isJudgeDemo('b_judge1'), true)
    const path = await startJudgeDemo(body, held, io)

    assert.equal(path, '/b/b_judge1/steps')
    assert.deepEqual(calls, [`create lifting-zone ${body.instruction}`, 'extract b_judge1', `patch b_judge1 ${body.instruction}`, 'extract b_judge1'])
  })

  it('the mark names one briefing: a second judge demo takes it over', () => {
    markJudgeDemo('b_one')
    markJudgeDemo('b_two')
    assert.deepEqual([isJudgeDemo('b_one'), isJudgeDemo('b_two')], [false, true])
  })
})

describe('with storage switched off', () => {
  it('nothing throws and no briefing counts as the judge demo (its handover opens unticked, as any other)', () => {
    const restore = useStorage('throws')
    try {
      assert.doesNotThrow(() => markJudgeDemo('b_judge1'))
      assert.equal(isJudgeDemo('b_judge1'), false)
    } finally {
      restore()
    }
  })
})

type Props = Record<string, unknown>
const ssr = await startSsr()
after(() => ssr.close())
const { I18nProvider } = await ssr.load<{ I18nProvider: ComponentType<Props> }>('/src/i18n/index.tsx')
const { CatalogProvider } = await ssr.load<{ CatalogProvider: ComponentType<Props> }>('/src/api/catalog.tsx')
const { FeedbackProvider } = await ssr.load<{ FeedbackProvider: ComponentType<Props> }>('/src/ui/FeedbackProvider.tsx')
// The page without its shell: the shell's daily-limit notice cannot be server-rendered (tests/helpers/stubs).
const { LandingContent } = await ssr.load<{ LandingContent: ComponentType }>('/src/screens/LandingScreen.tsx')
const { JudgeDemoScreen } = await ssr.load<{ JudgeDemoScreen: ComponentType }>('/src/screens/JudgeDemoScreen.tsx')

const landing = (lang: 'en' | 'ta' | 'zh') =>
  withUiLang(lang, () =>
    html(
      createElement(Router, {
        ssrPath: '/',
        children: createElement(I18nProvider, null, createElement(CatalogProvider, null, createElement(FeedbackProvider, null, createElement(LandingContent)))),
      }),
    ),
  )

/** Every <a>, as { href, cls, text }. */
const anchors = (markup: string) =>
  [...markup.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/g)].map((m) => ({
    href: /href="([^"]*)"/.exec(m[1] ?? '')?.[1],
    cls: (/class="([^"]*)"/.exec(m[1] ?? '')?.[1] ?? '').split(/\s+/),
    text: visibleText(m[2] ?? ''),
  }))

describe('the landing page link', () => {
  for (const [lang, table] of [['en', en], ['ta', ta], ['zh', zh]] as const) {
    it(`${lang}: "${table['judge.link']}" goes to /judge`, () => {
      const link = anchors(landing(lang)).find((a) => a.href === '/judge')
      assert.ok(link, 'no link to /judge')
      assert.equal(link.text, table['judge.link'])
    })
  }

  it('says what the review asked for, in English', () => {
    assert.equal(en['judge.link'], 'Run the 90-second judge demo')
  })

  it('adds no blue fill: Start a briefing stays the one solid blue action, and the link is blue text with a 48 px target', () => {
    const all = anchors(landing('en'))
    const filled = all.filter((a) => a.cls.includes('bg-primary'))
    assert.deepEqual(filled.map((a) => a.href), ['/new'])
    const link = all.find((a) => a.href === '/judge')
    assert.ok(link)
    assert.deepEqual(link.cls.filter((c) => c.startsWith('bg-')), [])
    assert.ok(link.cls.includes('text-primary') && link.cls.includes('underline') && link.cls.includes('min-h-12'))
  })
})

describe('the /judge screen', () => {
  const screen = withUiLang('en', () =>
    html(
      createElement(Router, {
        ssrPath: '/judge',
        children: createElement(I18nProvider, null, createElement(CatalogProvider, null, createElement(FeedbackProvider, null, createElement(JudgeDemoScreen)))),
      }),
    ),
  )

  it('is the route the landing link opens', () => {
    const app = readFileSync(new URL('../../src/App.tsx', import.meta.url), 'utf8')
    assert.match(app, /<Route path="\/judge" component=\{JudgeDemoScreen\} \/>/)
  })

  it('says what it sets up and shows the wait for the steps, with nothing to press', () => {
    const text = visibleText(screen)
    for (const key of ['judge.title', 'judge.subtitle', 'instr.extracting'] as const) assert.ok(text.includes(en[key]), `${key} is not on the screen`)
    assert.deepEqual(buttons(screen).filter((b) => /\bbg-primary\b/.test(b.attrs)).map((b) => b.text), [])
  })
})

describe('the handover of a judge-demo briefing', () => {
  // The screen loads its sample answers in an effect that SSR does not run, so this reads the source (as note 36-a did for the
  // library screen); the browser walk in note 37 shows the ticked box.
  const src = readFileSync(new URL('../../src/screens/brief/BriefScreen.tsx', import.meta.url), 'utf8')

  it('starts with "Use stored sample answers" chosen when the judge demo started this briefing, and unticked otherwise', () => {
    assert.match(src, /const judgeDemo = isJudgeDemo\(briefing\.id\)/)
    assert.match(src, /const \[sampleOn, setSampleOn\] = useState\(judgeDemo\)/)
  })

  it('says the stored answers are synthetic and analysed live, only on the judge demo and only when the samples are there', () => {
    assert.match(src, /\{judgeDemo && sampleOn && choice\.kind === 'available' && <Banner tone="info">\{t\('judge\.handover'\)\}<\/Banner>\}/)
    assert.match(en['judge.handover'], /synthetic Tamil voice/)
    assert.match(en['judge.handover'], /analyses them live/)
  })
})
