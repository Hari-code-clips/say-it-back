import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import type { DemoAnswer } from '../../src/api/types.ts'
import { HOLDER, resultMayOpen, secondsSince, stageOf, workerHolds, type GateInput, type RunKind, type Stage, type StageInput } from '../../src/screens/brief/handover.ts'
import { pairSamples, sampleChoice, sampleLoader, sampleQids, samplesFor, shouldAutoPlay, type RoundQuestion } from '../../src/screens/brief/sample.ts'

const input = (over: Partial<StageInput> = {}): StageInput => ({ run: 'ready', handed: false, tookOver: false, haveThePhone: false, ...over })

describe('F1: approving the script and handing the phone over are two acts', () => {
  it('after the approval the supervisor is on the handover step, not on the worker’s screen', () => {
    // The route is /b/:id/brief the moment the script is approved; the worker's Start appears only after "Give phone to worker".
    assert.equal(stageOf(input()), 'handover')
    assert.equal(HOLDER.handover, 'supervisor')
  })

  it('"Give phone to worker" is what brings up the worker’s Start', () => {
    assert.equal(stageOf(input({ handed: true })), 'worker_ready')
    assert.equal(HOLDER.worker_ready, 'worker')
  })

  it('ending the round, or taking the phone back from the Start screen, goes back to the handover, not to a worker screen', () => {
    assert.equal(stageOf(input({ handed: false, run: 'ready' })), 'handover')
  })
})

describe('who holds the phone, stage by stage', () => {
  const ALL: Stage[] = ['handover', 'worker_ready', 'worker_running', 'worker_failed', 'recovery', 'handback', 'checking']

  it('the worker holds Start, the session and a failure; the supervisor holds the handover, the recovery and the check’s wait', () => {
    assert.deepEqual(ALL.filter(workerHolds), ['worker_ready', 'worker_running', 'worker_failed'])
    assert.deepEqual(ALL.filter((s) => HOLDER[s] === 'supervisor'), ['handover', 'recovery', 'checking'])
    assert.equal(HOLDER.handback, 'transit')
  })

  it('every run state maps to a stage, whatever the supervisor has tapped', () => {
    const runs: RunKind[] = ['ready', 'running', 'failed', 'submitting', 'submit_failed']
    for (const run of runs) for (const handed of [false, true]) for (const tookOver of [false, true]) for (const haveThePhone of [false, true]) {
      assert.ok(ALL.includes(stageOf({ run, handed, tookOver, haveThePhone })))
    }
  })

  it('a running session is the worker’s, whatever else was tapped', () => {
    for (const tookOver of [false, true]) for (const haveThePhone of [false, true]) assert.equal(stageOf(input({ run: 'running', tookOver, haveThePhone })), 'worker_running')
  })
})

describe('F2: a failure shows the details only after the supervisor takes over', () => {
  it('a failed session shows the worker "give the phone to your supervisor", not the reason', () => {
    assert.equal(stageOf(input({ run: 'failed' })), 'worker_failed')
    assert.ok(workerHolds('worker_failed'))
  })

  it('the details and the recovery actions (turn mode, try again) belong to the supervisor’s stage', () => {
    assert.equal(stageOf(input({ run: 'failed', tookOver: true })), 'recovery')
    assert.equal(HOLDER.recovery, 'supervisor')
  })

  it('a check that failed after the last answer is not shown to the worker either: it waits for "I have the phone"', () => {
    assert.equal(stageOf(input({ run: 'submit_failed' })), 'handback')
    assert.equal(stageOf(input({ run: 'submit_failed', haveThePhone: true })), 'recovery')
  })
})

describe('F3: the hand-back gate', () => {
  it('after the last answer the worker is told to give the phone back, and the supervisor has not tapped yet', () => {
    assert.equal(stageOf(input({ run: 'submitting' })), 'handback')
  })

  it('"I have the phone" shows the check’s wait', () => {
    assert.equal(stageOf(input({ run: 'submitting', haveThePhone: true })), 'checking')
  })

  it('the result never opens before "I have the phone", however the check and the report stand', () => {
    for (const judged of [false, true]) for (const reportHolds of [false, true]) {
      assert.equal(resultMayOpen({ judged, haveThePhone: false, reportHolds }), false, `judged=${judged} reportHolds=${reportHolds}`)
    }
  })

  it('a check that is already done opens the result at once when the supervisor takes the phone', () => {
    assert.equal(resultMayOpen({ judged: true, haveThePhone: true, reportHolds: false }), true)
  })

  it('a check still running keeps the wait up after the tap: the result opens when it finishes', () => {
    assert.equal(resultMayOpen({ judged: false, haveThePhone: true, reportHolds: false }), false)
    // ...and then it finishes:
    assert.equal(resultMayOpen({ judged: true, haveThePhone: true, reportHolds: false }), true)
  })

  it('a worker’s problem report that is not sent yet still holds the page (v0.4 review)', () => {
    assert.equal(resultMayOpen({ judged: true, haveThePhone: true, reportHolds: true }), false)
  })

  it('opens in exactly one of the eight cases', () => {
    const open: GateInput[] = []
    for (const judged of [false, true]) for (const haveThePhone of [false, true]) for (const reportHolds of [false, true]) {
      if (resultMayOpen({ judged, haveThePhone, reportHolds })) open.push({ judged, haveThePhone, reportHolds })
    }
    assert.deepEqual(open, [{ judged: true, haveThePhone: true, reportHolds: false }])
  })

  it('counts the check’s elapsed time from when the request went out, not from the tap', () => {
    assert.equal(secondsSince(1_000, 1_000), 0)
    assert.equal(secondsSince(1_000, 22_999), 21)
    assert.equal(secondsSince(5_000, 1_000), 0) // a clock that stepped back never shows a negative time
  })
})

const question = (id: string, ...stepIds: string[]): RoundQuestion => ({ id, stepIds })
/** The lead demo's round-1 script (lifting-zone): where you stand (s1, s2), whose signals (s3), the swinging load (s4). */
const LEAD = [question('q1', 's1', 's2'), question('q2', 's3'), question('q3', 's4')]

describe('F1: the stored sample answers for this round (a server from before 16 Oct: one per round, no questionId)', () => {
  const ta = (taskId: string, round: number): DemoAnswer => ({ taskId, workerLang: 'ta', round, gloss: 'x' })
  const items = [ta('lifting-zone', 1), ta('lifting-zone', 2), { taskId: 'lifting-zone', workerLang: 'hi', round: 1, gloss: 'x' } as DemoAnswer]
  const qs = LEAD

  it('is offered when the server lists a clip for this task, worker language and round, and says it is for question 1 only', () => {
    const c = sampleChoice(items, true, 'lifting-zone', 'ta', 1, qs)
    assert.equal(c.kind, 'available')
    if (c.kind !== 'available') return
    assert.deepEqual(c.pairs.map((p) => p.qid), ['q1'])
    assert.deepEqual(c.numbers, [1])
    assert.equal(c.all, false)
  })

  it('answers the first question whatever its steps, since the old list names none', () => {
    const c = sampleChoice(items, true, 'lifting-zone', 'ta', 1, [question('q1', 's4'), question('q2', 's1')])
    assert.deepEqual(c.kind === 'available' && c.pairs.map((p) => p.qid), ['q1'])
  })

  it('says every question has one when the round has one question only', () => {
    const c = sampleChoice(items, true, 'lifting-zone', 'ta', 1, [question('q1', 's1', 's2')])
    assert.equal(c.kind === 'available' && c.all, true)
  })

  it('round 2 and every later round use the second clip', () => {
    for (const n of [2, 3]) assert.deepEqual(samplesFor(items, 'lifting-zone', 'ta', n).map((d) => d.round), [2])
  })

  it('is "none" when there is no clip for the task, the language or the round, or no question, or the list failed to load', () => {
    assert.equal(sampleChoice(items, true, 'scaffold-harness', 'ta', 1, qs).kind, 'none')
    assert.equal(sampleChoice(items, true, 'lifting-zone', 'bn', 1, qs).kind, 'none')
    assert.equal(sampleChoice(items, true, 'lifting-zone', 'ta', 1, []).kind, 'none')
    assert.equal(sampleChoice(undefined, true, 'lifting-zone', 'ta', 1, qs).kind, 'none')
  })

  it('is "loading" until the list has loaded', () => {
    assert.equal(sampleChoice(undefined, false, 'lifting-zone', 'ta', 1, qs).kind, 'loading')
  })

  it('plays nowhere unless the supervisor chose it', () => {
    const c = sampleChoice(items, true, 'lifting-zone', 'ta', 1, qs)
    assert.deepEqual(sampleQids(false, c), [])
    assert.deepEqual(sampleQids(true, c), ['q1'])
  })

  it('plays nowhere when there is no stored sample, even if the box was ticked before', () => {
    const none = sampleChoice(items, true, 'scaffold-harness', 'ta', 1, qs)
    assert.deepEqual(sampleQids(true, none), [])
    assert.deepEqual(sampleQids(true, sampleChoice(undefined, false, 'lifting-zone', 'ta', 1, qs)), [])
  })

  it('is played as the answer window of question 1 opens, and for no other window or phase', () => {
    const qids = sampleQids(true, sampleChoice(items, true, 'lifting-zone', 'ta', 1, qs))
    assert.equal(shouldAutoPlay(qids, { kind: 'listening', qid: 'q1' }), true)
    assert.equal(shouldAutoPlay(qids, { kind: 'listening', qid: 'q2' }), false) // no stored sample for question 2: the worker answers normally
    assert.equal(shouldAutoPlay(qids, { kind: 'listening', qid: 'q3' }), false)
    assert.equal(shouldAutoPlay(qids, { kind: 'speaking', qid: 'q1' }), false) // the question is still being asked
    assert.equal(shouldAutoPlay(qids, { kind: 'connecting' }), false)
    assert.equal(shouldAutoPlay([], { kind: 'listening', qid: 'q1' }), false)
  })
})

describe('16 Oct: a stored answer for every question, paired with the round\'s questions by the steps they share', () => {
  const answer = (task: string, lang: DemoAnswer['workerLang'], round: number, qid: string, ...stepIds: string[]): DemoAnswer => ({
    taskId: task, workerLang: lang, round, gloss: `r${round} ${qid}`, questionId: qid, stepIds,
  })
  // What the server lists for both demos (reference question order within a round), as endpoint 24 does since 16 Oct.
  const LIST = [1, 2].flatMap((n) => [
    answer('lifting-zone', 'ta', n, 'q1', 's1', 's2'), answer('lifting-zone', 'ta', n, 'q2', 's3'), answer('lifting-zone', 'ta', n, 'q3', 's4'),
    answer('scaffold-harness', 'hi', n, 'q1', 's1', 's2'), answer('scaffold-harness', 'hi', n, 'q2', 's3'),
  ])
  const paired = (questions: RoundQuestion[], n = 1, task = 'lifting-zone', lang = 'ta') =>
    pairSamples(questions, samplesFor(LIST, task, lang, n)).map((p) => [p.qid, p.item.gloss])

  it('all covered: each question of the lead demo gets its own stored answer, and the choice says every question has one', () => {
    assert.deepEqual(paired(LEAD), [['q1', 'r1 q1'], ['q2', 'r1 q2'], ['q3', 'r1 q3']])
    const c = sampleChoice(LIST, true, 'lifting-zone', 'ta', 1, LEAD)
    assert.deepEqual(c.kind === 'available' && [c.numbers, c.all], [[1, 2, 3], true])
    assert.deepEqual(sampleQids(true, c), ['q1', 'q2', 'q3'])
    for (const qid of ['q1', 'q2', 'q3']) assert.equal(shouldAutoPlay(sampleQids(true, c), { kind: 'listening', qid }), true, qid)
  })

  it('round 2 and every later round use the second round\'s answers, also for a re-explain round\'s new question ids', () => {
    for (const n of [2, 3]) assert.deepEqual(paired(LEAD, n), [['q1', 'r2 q1'], ['q2', 'r2 q2'], ['q3', 'r2 q3']], `round ${n}`)
    const reexplain = [question('q4', 's1', 's2'), question('q5', 's4')]
    assert.deepEqual(paired(reexplain, 2), [['q4', 'r2 q1'], ['q5', 'r2 q3']])
    const c = sampleChoice(LIST, true, 'lifting-zone', 'ta', 2, reexplain)
    assert.deepEqual(c.kind === 'available' && [c.numbers, c.all], [[1, 2], true])
  })

  it('partial: a question with no answer left to share a step with is the worker\'s own voice, and the choice names the others', () => {
    // The second demo written as three questions: q1's answer covers s1 and s2, so only one of [s1] and [s2] can have it.
    const three = [question('q1', 's1'), question('q2', 's2'), question('q3', 's3')]
    assert.deepEqual(paired(three, 1, 'scaffold-harness', 'hi'), [['q1', 'r1 q1'], ['q3', 'r1 q2']])
    const c = sampleChoice(LIST, true, 'scaffold-harness', 'hi', 1, three)
    assert.deepEqual(c.kind === 'available' && [c.numbers, c.all], [[1, 3], false])
    assert.equal(shouldAutoPlay(sampleQids(true, c), { kind: 'listening', qid: 'q2' }), false)
  })

  it('tie: two answers share as many steps with a question, so the one listed first (reference question order) is played', () => {
    assert.deepEqual(paired([question('q4', 's3', 's4')], 2), [['q4', 'r2 q2']])
  })

  it('pairs the whole round, so a tie on an early question never takes the only answer a later one could use', () => {
    // Question by question, [s2, s4] would take the s1+s2 answer (listed first) and leave [s1] with nothing.
    assert.deepEqual(paired([question('q4', 's2', 's4'), question('q5', 's1')], 2), [['q4', 'r2 q3'], ['q5', 'r2 q1']])
  })

  it('zero overlap: an answer goes only to a question it shares a step with, and each answer is used once', () => {
    assert.deepEqual(paired([question('q1', 's9')]), [])
    assert.equal(sampleChoice(LIST, true, 'lifting-zone', 'ta', 1, [question('q1', 's9')]).kind, 'none')
    assert.deepEqual(paired([question('q1', 's3'), question('q2', 's3')]), [['q1', 'r1 q2']])
    assert.deepEqual(paired([question('q1', 's9'), ...LEAD.slice(1)]), [['q2', 'r1 q2'], ['q3', 'r1 q3']])
  })

  it('never says "every question" when a step is in no paired answer (review of 16 Oct): it says that step may need a round', () => {
    // Round 1 written as two questions: [s1, s2] gets the s1+s2 answer, [s3, s4] only one of the s3 and s4 answers.
    const two = [question('q1', 's1', 's2'), question('q2', 's3', 's4')]
    const c = sampleChoice(LIST, true, 'lifting-zone', 'ta', 1, two)
    assert.deepEqual(c.kind === 'available' && [c.numbers, c.all, c.stepsLeft], [[1, 2], false, true])
    // A re-explain that bundles three steps into one question gets one answer, with s4 in none.
    const one = sampleChoice(LIST, true, 'lifting-zone', 'ta', 2, [question('q4', 's1', 's2', 's4')])
    assert.deepEqual(one.kind === 'available' && [one.all, one.stepsLeft], [false, true])
    // The lead demo as written stays "every question", with no step left.
    const lead = sampleChoice(LIST, true, 'lifting-zone', 'ta', 1, LEAD)
    assert.deepEqual(lead.kind === 'available' && [lead.all, lead.stepsLeft], [true, false])
  })

  it('offers nothing for another task, language or a list that failed', () => {
    assert.equal(sampleChoice(LIST, true, 'panel-isolation', 'ta', 1, LEAD).kind, 'none')
    assert.equal(sampleChoice(LIST, true, 'lifting-zone', 'hi', 1, LEAD).kind, 'none')
    assert.equal(sampleChoice(undefined, true, 'lifting-zone', 'ta', 1, LEAD).kind, 'none')
  })
})

describe('16 Oct: every paired clip is fetched once, ahead of the choice', () => {
  const item = (qid: string): DemoAnswer => ({ taskId: 'lifting-zone', workerLang: 'ta', round: 1, gloss: qid, questionId: qid, stepIds: [] })
  const pairs = [{ qid: 'q1', item: item('q1') }, { qid: 'q3', item: item('q3') }]

  it('asks the server once per question, gives the same clip every time, and nothing for a question with no answer', async () => {
    const asked: string[] = []
    const load = sampleLoader(pairs, async (d) => {
      asked.push(d.questionId ?? '')
      return new Blob([d.gloss])
    })
    const first = load('q1')
    assert.equal(load('q1'), first)
    assert.equal(await (await first)?.text(), 'q1')
    assert.equal(await (await load('q3'))?.text(), 'q3')
    assert.equal(load('q2'), undefined)
    assert.deepEqual(asked, ['q1', 'q3'])
  })

  it('tries a failed fetch again on the next call', async () => {
    let calls = 0
    const load = sampleLoader(pairs, async () => {
      calls += 1
      if (calls === 1) throw new Error('offline')
      return new Blob(['ok'])
    })
    await assert.rejects(load('q1') as Promise<Blob>)
    await new Promise((resolve) => setTimeout(resolve, 0)) // the failed promise is forgotten after it settles
    assert.equal(await (await load('q1'))?.text(), 'ok')
    assert.equal(calls, 2)
  })
})
