import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { after, before, describe, it } from 'node:test'
import type { DemoAnswer, Lang, SiteId } from '../../src/api/types.ts'
import { translate } from '../../src/i18n/translate.ts'
import { speechWav } from '../../src/mock/audio.ts'
import { publicCatalog, rawDemoScript, roundAnswers } from '../../src/mock/catalog.ts'
import { mockFetch } from '../../src/mock/handlers.ts'
import * as store from '../../src/mock/store.ts'
import { HttpError } from '../../src/mock/util.ts'
import { pairSamples, samplesFor } from '../../src/screens/brief/sample.ts'

// 16 Oct breadth (build-notes/34-breadth.md): dev:mock walks hot work in Bengali and trench entry in Odia with the catalog's stored
// answers, and English is offered on both sites for an evaluator who plays the worker (never as a worker language of the product).

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

interface Demo {
  script: string
  siteId: SiteId
  taskId: string
  supervisorLang: Lang
  workerLang: Lang
  round1: Record<string, string>
  round2: [string, string[]][]
}

const DEMOS: Demo[] = [
  { script: 'sg-hot-work', siteId: 'sg', taskId: 'hot-work', supervisorLang: 'en', workerLang: 'bn',
    round1: { s1: 'covered', s2: 'covered', s3: 'contradicted' }, round2: [['q3', ['s3']]] },
  { script: 'chennai-trench', siteId: 'chennai', taskId: 'trench-entry', supervisorLang: 'ta', workerLang: 'or',
    round1: { s1: 'missed', s2: 'covered', s3: 'covered' }, round2: [['q3', ['s1']]] },
]

const line = (d: Demo, n: number, qid: string) => roundAnswers(rawDemoScript(d.script)?.rounds[n - 1]).find((a) => a.questionId === qid)?.answer[d.workerLang]

const quotesAreSaid = (round: ReturnType<typeof store.checkRound>) => {
  for (const r of round.ratings) {
    for (const part of (r.quote ?? '').split('...')) assert.ok(round.transcripts.some((t) => t.original.includes(part.trim())), r.stepId)
  }
}

describe('mock breadth demos: the stored answers say the catalog\'s lines, one step wrong in round 1', () => {
  for (const d of DEMOS) {
    it(`${d.script}: round 1 in Turn mode with stored answers, then round 2 covers the open step`, () => {
      const b = store.createBriefing({ siteId: d.siteId, taskId: d.taskId, supervisorLang: d.supervisorLang, workerLang: d.workerLang, instruction: 'Follow the SOP.' })
      store.confirmSteps(b.id, store.extractSteps(b.id).steps)
      const r1 = store.createRound(b.id, {})
      store.approveRound(b.id, 1)
      assert.deepEqual(r1.script.questions.map((q) => [q.id, q.stepIds]), [['q1', ['s1', 's2']], ['q2', ['s3']]])
      const one = store.checkRound(b.id, 1, { q1: answer(), q2: answer() }, 'turn', ['q1', 'q2'])

      assert.deepEqual(Object.fromEntries(one.ratings.map((r) => [r.stepId, r.verdict])), d.round1)
      assert.deepEqual(one.transcripts.map((t) => [t.original, t.detectedLang]), [[line(d, 1, 'q1'), d.workerLang], [line(d, 1, 'q2'), d.workerLang]])
      quotesAreSaid(one)

      const r2 = store.createRound(b.id, {})
      assert.deepEqual(r2.script.questions.map((q) => [q.id, q.stepIds]), d.round2)
      store.approveRound(b.id, 2)
      const two = store.checkRound(b.id, 2, { q3: answer() }, 'turn', ['q3'])
      assert.ok(two.ratings.every((r) => r.verdict === 'covered'))
      assert.equal(two.transcripts[0]?.original, line(d, 2, d.round2[0]?.[1].includes('s3') ? 'q2' : 'q1'))
      quotesAreSaid(two)
    })
  }

  it('endpoint 24 pairs every question of both rounds with its own stored answer, and serves each clip', async () => {
    const items = await listed()
    for (const d of DEMOS) {
      for (const n of [1, 2]) {
        const questions = [{ id: 'q1', text: '', stepIds: ['s1', 's2'] }, { id: 'q2', text: '', stepIds: ['s3'] }]
        const pairs = pairSamples(questions, samplesFor(items, d.taskId, d.workerLang, n))
        assert.deepEqual(pairs.map((p) => [p.qid, p.item.questionId]), [['q1', 'q1'], ['q2', 'q2']], `${d.script} round ${n}`)
        const res = await get(`/demo-answers/${d.taskId}/${d.workerLang}/${n}/q2/audio`)
        assert.equal(res.headers.get('Content-Type'), 'audio/wav')
      }
    }
  })
})

describe('English for evaluators', () => {
  it('both sites offer it after their worker languages, never as one of them', () => {
    for (const site of publicCatalog.sites) {
      assert.deepEqual(site.evaluatorLanguages, ['en'], site.id)
      assert.ok(!site.workerLanguages.includes('en'), site.id)
    }
  })

  it('the mock briefs an English worker on both sites, and still refuses a language a site does not offer', () => {
    const sg = store.createBriefing({ siteId: 'sg', taskId: 'lifting-zone', supervisorLang: 'en', workerLang: 'en', instruction: 'Never go under the load.' })
    const chennai = store.createBriefing({ siteId: 'chennai', taskId: 'trench-entry', supervisorLang: 'ta', workerLang: 'en', instruction: 'Use only the ladder.' })
    assert.deepEqual([sg.workerLang, chennai.workerLang], ['en', 'en'])
    assert.throws(
      () => store.createBriefing({ siteId: 'sg', taskId: 'lifting-zone', supervisorLang: 'en', workerLang: 'hi', instruction: 'Never go under the load.' }),
      (e: unknown) => e instanceof HttpError && e.code === 'unsupported_language',
    )
  })

  it('an English worker hears plain English (no mock marker) and is heard in English', () => {
    const b = store.createBriefing({ siteId: 'sg', taskId: 'custom', supervisorLang: 'en', workerLang: 'en', instruction: 'Wear the mask. Check the seal before you start.', sop: { title: 'Spray painting', text: 'Wear a fitted respirator and check its seal before spraying.' } })
    store.confirmSteps(b.id, store.extractSteps(b.id).steps)
    const r1 = store.createRound(b.id, {})
    store.approveRound(b.id, 1)
    assert.ok(!r1.script.instruction.includes('mock]'), r1.script.instruction)
    const qids = r1.script.questions.map((q) => q.id)
    const one = store.checkRound(b.id, 1, Object.fromEntries(qids.map((q) => [q, answer()])), 'turn', [])
    assert.ok(one.transcripts.every((t) => t.detectedLang === 'en'))
  })

  it('is labelled for evaluators in the supervisor\'s language, offered last on the Start screen, and named on the landing page', () => {
    assert.equal(translate('en', 'breadth.evaluatorLang', { lang: 'English' }), 'English (for evaluators)')
    assert.equal(translate('ta', 'breadth.evaluatorLang', { lang: 'ஆங்கிலம்' }), 'ஆங்கிலம் (மதிப்பீட்டாளர்களுக்கு)')
    assert.equal(translate('zh', 'breadth.evaluatorLang', { lang: '英语' }), '英语（供评审使用）')
    assert.match(translate('en', 'breadth.tryOwn'), /^Try it with your own procedure: choose English \(for evaluators\)/)
    for (const lang of ['ta', 'zh']) assert.match(source(`i18n/${lang}/breadth.ts`), /DRAFT.*NEEDS NATIVE-SPEAKER REVIEW/)

    const start = source('screens/StartScreen.tsx')
    const workers = start.indexOf('...site.workerLanguages.map(')
    const evaluators = start.indexOf("...(site.evaluatorLanguages ?? []).map((l) => ({ value: l, label: t('breadth.evaluatorLang'")
    assert.ok(workers > 0 && evaluators > workers, 'English (for evaluators) comes after the worker languages')
    assert.ok(source('screens/LandingScreen.tsx').includes("t('breadth.tryOwn')"))
  })
})
