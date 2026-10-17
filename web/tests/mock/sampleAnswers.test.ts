import assert from 'node:assert/strict'
import { after, before, describe, it } from 'node:test'
import type { DemoAnswer } from '../../src/api/types.ts'
import { speechWav } from '../../src/mock/audio.ts'
import { rawDemoScript, roundAnswers } from '../../src/mock/catalog.ts'
import { mockFetch } from '../../src/mock/handlers.ts'
import * as store from '../../src/mock/store.ts'
import { HttpError } from '../../src/mock/util.ts'
import { pairSamples, samplesFor } from '../../src/screens/brief/sample.ts'

// 16 Oct (build-notes/30): dev:mock serves a stored answer for every question of the two demos on the server's own paths, and the
// lead demo's scripted results are the catalog's new lines: round 1 s1 Wrong, s2 Missed, s3 Got it, s4 Wrong; round 2 all Got it.

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

describe('mock endpoint 24: one stored answer per question, on the server\'s paths', () => {
  it('lists each demo round\'s answers with their question and its steps, in reference question order', async () => {
    const items = await listed()
    const rows = items.map((d) => `${d.taskId} ${d.workerLang} r${d.round} ${d.questionId} ${d.stepIds?.join('+')}`)
    assert.deepEqual(rows, [
      'lifting-zone ta r1 q1 s1+s2', 'lifting-zone ta r1 q2 s3', 'lifting-zone ta r1 q3 s4',
      'lifting-zone ta r2 q1 s1+s2', 'lifting-zone ta r2 q2 s3', 'lifting-zone ta r2 q3 s4',
      'panel-isolation ta r1 q1 s1+s2+s3', 'panel-isolation ta r2 q1 s1+s2+s3',
      'scaffold-harness hi r1 q1 s1+s2', 'scaffold-harness hi r1 q2 s3',
      'scaffold-harness hi r2 q1 s1+s2', 'scaffold-harness hi r2 q2 s3',
      // 16 Oct breadth (build-notes/34-breadth.md): hot work in Bengali, trench entry in Odia.
      'hot-work bn r1 q1 s1+s2', 'hot-work bn r1 q2 s3', 'hot-work bn r2 q1 s1+s2', 'hot-work bn r2 q2 s3',
      'trench-entry or r1 q1 s1+s2', 'trench-entry or r1 q2 s3', 'trench-entry or r2 q1 s1+s2', 'trench-entry or r2 q2 s3',
      // 17 Oct demo suites (build-notes/37-domain-suites.md): four more work domains.
      'hydro-jetting bn r1 q1 s1+s2', 'hydro-jetting bn r1 q2 s3', 'hydro-jetting bn r2 q1 s1+s2', 'hydro-jetting bn r2 q2 s3',
      'steam-line-break ta r1 q1 s1+s2', 'steam-line-break ta r1 q2 s3', 'steam-line-break ta r2 q1 s1+s2', 'steam-line-break ta r2 q2 s3',
      'press-lockout hi r1 q1 s1+s2+s3', 'press-lockout hi r1 q2 s4', 'press-lockout hi r2 q1 s1+s2+s3', 'press-lockout hi r2 q2 s4',
      'telecom-tower te r1 q1 s1+s2', 'telecom-tower te r1 q2 s3', 'telecom-tower te r2 q1 s1+s2', 'telecom-tower te r2 q2 s3',
    ])
    assert.equal(items[2]?.gloss, "If the load swings, I'll grab it with my hand and stop it swinging.")
  })

  it('serves each question\'s clip, the round\'s own answer on the older route, round 2 for every later round, else 404', async () => {
    for (const path of ['/demo-answers/lifting-zone/ta/1/q3/audio', '/demo-answers/lifting-zone/ta/1/audio', '/demo-answers/scaffold-harness/hi/3/q2/audio']) {
      const res = await get(path)
      assert.equal(res.status, 200, path)
      assert.equal(res.headers.get('Content-Type'), 'audio/wav', path)
    }
    for (const path of ['/demo-answers/lifting-zone/ta/1/q9/audio', '/demo-answers/panel-isolation/ta/1/q2/audio', '/demo-answers/lifting-zone/ta/0/q1/audio']) {
      const res = await get(path)
      assert.equal(res.status, 404, path)
      assert.equal(((await res.json()) as { error: { code: string } }).error.code, 'no_demo_answer', path)
    }
  })

  it('pairs every question of the lead demo\'s first round with its own stored answer in the web\'s mapping', async () => {
    const lead = store.createBriefing({ siteId: 'sg', taskId: 'lifting-zone', supervisorLang: 'en', workerLang: 'ta', instruction: 'Never go under the load.' })
    store.confirmSteps(lead.id, store.extractSteps(lead.id).steps)
    const round = store.createRound(lead.id, {})
    const pairs = pairSamples(round.script.questions, samplesFor(await listed(), 'lifting-zone', 'ta', 1))
    assert.deepEqual(pairs.map((p) => [p.qid, p.item.questionId]), [['q1', 'q1'], ['q2', 'q2'], ['q3', 'q3']])
  })
})

describe('mock lead demo: the stored answers say the catalog\'s lines, and the results follow them', () => {
  const answer = () => speechWav(3, 16_000, 7)
  const refused = (code: string) => (e: unknown) => e instanceof HttpError && e.code === code
  const catalogLine = (n: number, qid: string) => roundAnswers(rawDemoScript('sg-lead')?.rounds[n - 1]).find((a) => a.questionId === qid)?.answer.ta

  it('round 1 in Turn mode with every answer a sample: s1 Wrong, s2 Missed, s3 Got it, s4 Wrong; round 2: all Got it; Go needs a reason', () => {
    const b = store.createBriefing({ siteId: 'sg', taskId: 'lifting-zone', supervisorLang: 'en', workerLang: 'ta', instruction: 'Never go under the load.' })
    store.confirmSteps(b.id, store.extractSteps(b.id).steps)
    const r1 = store.createRound(b.id, {})
    store.approveRound(b.id, 1)
    const qids = r1.script.questions.map((q) => q.id)
    const one = store.checkRound(b.id, 1, Object.fromEntries(qids.map((q) => [q, answer()])), 'turn', qids)

    assert.deepEqual(Object.fromEntries(one.ratings.map((r) => [r.stepId, r.verdict])), { s1: 'contradicted', s2: 'missed', s3: 'covered', s4: 'contradicted' })
    assert.deepEqual(one.transcripts.map((t) => t.original), [catalogLine(1, 'q1'), catalogLine(1, 'q2'), catalogLine(1, 'q3')])
    for (const r of one.ratings.filter((x) => x.quote)) assert.ok(one.transcripts.some((t) => t.original.includes(r.quote ?? '')), r.stepId)
    assert.deepEqual(one.sampleAnswers, ['q1', 'q2', 'q3'])

    const r2 = store.createRound(b.id, {})
    assert.deepEqual(r2.script.questions.map((q) => [q.id, q.stepIds]), [['q4', ['s1', 's2']], ['q5', ['s4']]])
    store.approveRound(b.id, 2)
    const two = store.checkRound(b.id, 2, Object.fromEntries(r2.script.questions.map((q) => [q.id, answer()])), 'turn', ['q4', 'q5'])
    assert.ok(two.ratings.every((r) => r.verdict === 'covered'))
    assert.deepEqual(two.transcripts.map((t) => t.original), [catalogLine(2, 'q1'), catalogLine(2, 'q3')])
    for (const r of two.ratings) for (const part of (r.quote ?? '').split('...')) assert.ok(two.transcripts.some((t) => t.original.includes(part.trim())), r.stepId)

    // Every step was said back only by a stored sample: open at the decision, so Go needs a reason (sample-covered by design).
    assert.deepEqual(store.getBriefing(b.id).sampleCoveredStepIds, ['s1', 's2', 's3', 's4'])
    assert.throws(() => store.decide(b.id, { value: 'go' }), refused('reason_required'))
  })
})
