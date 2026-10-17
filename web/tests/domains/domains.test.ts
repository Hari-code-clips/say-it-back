import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { after, before, describe, it } from 'node:test'
import type { DemoAnswer, Lang, SiteId } from '../../src/api/types.ts'
import { TASK_ICONS } from '../../src/api/taskIcons.ts'
import { taskTitle } from '../../src/i18n/catalogText.ts'
import { translate } from '../../src/i18n/translate.ts'
import { speechWav } from '../../src/mock/audio.ts'
import { publicCatalog, rawDemoScript, roundAnswers } from '../../src/mock/catalog.ts'
import { mockFetch } from '../../src/mock/handlers.ts'
import * as store from '../../src/mock/store.ts'
import { pairSamples, samplesFor } from '../../src/screens/brief/sample.ts'
import { DOMAIN_KEYS, domainKey, groupByHeading } from '../../src/screens/start/taskPickerState.ts'

// 17 Oct demo suites (build-notes/37-domain-suites.md): four more work domains, each a task with a demo script that dev:mock plays
// with the catalog's stored answers (one step wrong in round 1, every step covered in round 2), and the Start screen's task picker
// lists every task under its domain's heading.

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

const get = (path: string) => mockFetch(`/api${path}`, { headers: { 'X-SIB-Device': 'mock-test-device-key-0001' } })
const listed = async (): Promise<DemoAnswer[]> => ((await (await get('/demo-answers')).json()) as { items: DemoAnswer[] }).items
const answer = () => speechWav(3, 16_000, 7)
const source = (path: string) => readFileSync(new URL(`../../src/${path}`, import.meta.url), 'utf8')

interface Suite {
  script: string
  siteId: SiteId
  taskId: string
  domain: string
  supervisorLang: Lang
  workerLang: Lang
  questions: [string, string[]][]
  round1: Record<string, string>
  /** The re-explain round's question over the open step, and the round-2 answer that says it. */
  round2: [string, string[], string]
}

const SUITES: Suite[] = [
  { script: 'sg-hydrojet', siteId: 'sg', taskId: 'hydro-jetting', domain: 'marine', supervisorLang: 'en', workerLang: 'bn',
    questions: [['q1', ['s1', 's2']], ['q2', ['s3']]], round1: { s1: 'covered', s2: 'contradicted', s3: 'covered' }, round2: ['q3', ['s2'], 'q1'] },
  { script: 'sg-steam-line', siteId: 'sg', taskId: 'steam-line-break', domain: 'process', supervisorLang: 'en', workerLang: 'ta',
    questions: [['q1', ['s1', 's2']], ['q2', ['s3']]], round1: { s1: 'contradicted', s2: 'covered', s3: 'covered' }, round2: ['q3', ['s1'], 'q1'] },
  { script: 'chennai-press', siteId: 'chennai', taskId: 'press-lockout', domain: 'manufacturing', supervisorLang: 'ta', workerLang: 'hi',
    questions: [['q1', ['s1', 's2', 's3']], ['q2', ['s4']]], round1: { s1: 'covered', s2: 'covered', s3: 'covered', s4: 'contradicted' }, round2: ['q3', ['s4'], 'q2'] },
  { script: 'chennai-tower', siteId: 'chennai', taskId: 'telecom-tower', domain: 'telecom', supervisorLang: 'ta', workerLang: 'te',
    questions: [['q1', ['s1', 's2']], ['q2', ['s3']]], round1: { s1: 'covered', s2: 'missed', s3: 'covered' }, round2: ['q3', ['s2'], 'q1'] },
]

const line = (s: Suite, n: number, qid: string) => roundAnswers(rawDemoScript(s.script)?.rounds[n - 1]).find((a) => a.questionId === qid)?.answer[s.workerLang]

const quotesAreSaid = (round: ReturnType<typeof store.checkRound>) => {
  for (const r of round.ratings) {
    for (const part of (r.quote ?? '').split('...')) assert.ok(round.transcripts.some((t) => t.original.includes(part.trim())), r.stepId)
  }
}

describe('mock demo suites: the stored answers say the catalog\'s lines, one step wrong in round 1', () => {
  for (const s of SUITES) {
    it(`${s.script}: round 1 in Turn mode with stored answers, then the re-explain round covers the open step`, () => {
      const b = store.createBriefing({ siteId: s.siteId, taskId: s.taskId, supervisorLang: s.supervisorLang, workerLang: s.workerLang, instruction: 'Follow the SOP.' })
      store.confirmSteps(b.id, store.extractSteps(b.id).steps)
      const r1 = store.createRound(b.id, {})
      store.approveRound(b.id, 1)
      assert.deepEqual(r1.script.questions.map((q) => [q.id, q.stepIds]), s.questions)
      assert.ok(!r1.script.instruction.includes('mock]'), r1.script.instruction) // the suite's own worker-language lines
      const one = store.checkRound(b.id, 1, { q1: answer(), q2: answer() }, 'turn', ['q1', 'q2'])

      assert.deepEqual(Object.fromEntries(one.ratings.map((r) => [r.stepId, r.verdict])), s.round1)
      assert.deepEqual(one.transcripts.map((t) => [t.original, t.detectedLang]), [[line(s, 1, 'q1'), s.workerLang], [line(s, 1, 'q2'), s.workerLang]])
      quotesAreSaid(one)

      const r2 = store.createRound(b.id, {})
      assert.deepEqual(r2.script.questions.map((q) => [q.id, q.stepIds]), [s.round2.slice(0, 2)])
      store.approveRound(b.id, 2)
      const two = store.checkRound(b.id, 2, { q3: answer() }, 'turn', ['q3'])
      assert.ok(two.ratings.every((r) => r.verdict === 'covered'), JSON.stringify(two.ratings))
      assert.equal(two.transcripts[0]?.original, line(s, 2, s.round2[2]))
      quotesAreSaid(two)
    })
  }

  it('endpoint 24 pairs every question of both rounds with its own stored answer, and serves each clip', async () => {
    const items = await listed()
    for (const s of SUITES) {
      for (const n of [1, 2]) {
        const questions = s.questions.map(([id, stepIds]) => ({ id, text: '', stepIds }))
        const pairs = pairSamples(questions, samplesFor(items, s.taskId, s.workerLang, n))
        assert.deepEqual(pairs.map((p) => [p.qid, p.item.questionId]), [['q1', 'q1'], ['q2', 'q2']], `${s.script} round ${n}`)
        const res = await get(`/demo-answers/${s.taskId}/${s.workerLang}/${n}/q2/audio`)
        assert.equal(res.headers.get('Content-Type'), 'audio/wav')
      }
    }
  })

  it('the suites are briefed on their own sites, and a site still refuses a language it does not offer', () => {
    for (const s of SUITES) {
      const site = publicCatalog.sites.find((x) => x.id === s.siteId)
      assert.ok(site?.workerLanguages.includes(s.workerLang), s.script)
      assert.ok(site?.supervisorLanguages.includes(s.supervisorLang), s.script)
    }
    assert.throws(() => store.createBriefing({ siteId: 'sg', taskId: 'telecom-tower', supervisorLang: 'en', workerLang: 'te', instruction: 'Stay hooked on.' }))
  })
})

describe('the task picker lists every task under its domain', () => {
  const t = (lang: 'en' | 'ta' | 'zh', domain: string) => {
    const key = domainKey(domain)
    assert.ok(key, domain)
    return translate(lang, key)
  }

  it('every catalog task names a known domain, the suites theirs, and the public catalog carries it', () => {
    for (const task of publicCatalog.tasks) assert.ok(task.domain && domainKey(task.domain), task.id)
    for (const s of SUITES) assert.equal(publicCatalog.tasks.find((x) => x.id === s.taskId)?.domain, s.domain)
    assert.equal(publicCatalog.tasks.find((x) => x.id === 'confined-space')?.domain, 'utilities')
    assert.deepEqual(Object.keys(DOMAIN_KEYS), ['construction', 'utilities', 'marine', 'process', 'manufacturing', 'telecom'])
  })

  it('one heading per domain in the order each first appears, every task kept once, your own SOP last', () => {
    const options = [
      ...publicCatalog.tasks.map((task) => ({ value: task.id, group: t('en', task.domain ?? '') })),
      { value: 'custom', group: translate('en', 'domain.own') },
    ]
    const groups = groupByHeading(options)
    assert.deepEqual(groups.map((g) => g.heading), ['Construction', 'Utilities', 'Marine', 'Process plant', 'Manufacturing', 'Telecom', 'Your own procedure'])
    assert.deepEqual(groups[0]?.items.map((o) => o.value), ['lifting-zone', 'panel-isolation', 'scaffold-harness', 'hot-work', 'trench-entry', 'fragile-roof'])
    assert.deepEqual(groups.flatMap((g) => g.items.map((o) => o.value)).sort(), options.map((o) => o.value).sort())
    const plain: { value: string; group?: string }[] = [{ value: 'a' }, { value: 'b' }]
    assert.deepEqual(groupByHeading(plain), [{ heading: undefined, items: plain }]) // no domains: the list as it was
  })

  it('names each domain in English, Tamil and Chinese, the drafts marked for native review', () => {
    for (const domain of Object.keys(DOMAIN_KEYS)) {
      const names = (['en', 'ta', 'zh'] as const).map((lang) => t(lang, domain))
      assert.equal(new Set(names).size, 3, domain)
    }
    assert.equal(t('ta', 'marine'), 'கப்பல் துறை')
    assert.equal(t('zh', 'telecom'), '通信')
    for (const lang of ['ta', 'zh']) assert.match(source(`i18n/${lang}/domains.ts`), /DRAFT.*NEEDS NATIVE-SPEAKER REVIEW/)
  })

  it('each new task has its own icon and a Chinese title', () => {
    for (const s of SUITES) {
      const task = publicCatalog.tasks.find((x) => x.id === s.taskId)
      assert.ok(task && task.icon in TASK_ICONS, s.taskId)
      assert.notEqual(taskTitle({ id: s.taskId, title: { en: task?.title.en ?? '' } }, 'zh'), task?.title.en, s.taskId)
    }
    assert.equal(new Set(publicCatalog.tasks.map((x) => TASK_ICONS[x.icon])).size, publicCatalog.tasks.length)
  })

  it('the Start screen heads each task by its domain and the custom SOP by its own heading, only when the server sends domains', () => {
    const start = source('screens/StartScreen.tsx')
    assert.match(start, /group: domainHeading\(task\.domain\)/)
    assert.match(start, /group: grouped \? t\('domain\.own'\) : undefined/)
    const picker = source('screens/start/TaskPicker.tsx')
    assert.match(picker, /role=\{g\.heading \? 'group' : undefined\}/)
    assert.match(picker, /aria-labelledby=\{g\.heading \? `\$\{listId\}-g\$\{i\}` : undefined\}/)
    assert.doesNotMatch(picker, /role="radiogroup"/) // a heading may not sit inside a radiogroup
  })
})
