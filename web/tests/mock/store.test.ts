import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { speechWav } from '../../src/mock/audio.ts'
import * as store from '../../src/mock/store.ts'
import { HttpError } from '../../src/mock/util.ts'

// The mock backend in node: it keeps state in memory when sessionStorage is not there. It must play the v0.4 contract faithfully,
// because the demo, the screenshots and the deck are made from it.

const answer = () => speechWav(3, 16_000, 7)

const refused = (code: string) => (e: unknown) => e instanceof HttpError && e.code === code

function leadBriefing() {
  const b = store.createBriefing({
    siteId: 'sg', taskId: 'lifting-zone', supervisorLang: 'en', workerLang: 'ta',
    instruction: "Never go under the load, stay outside the barrier until it's landed, and only follow the signalman.",
  })
  const proposed = store.extractSteps(b.id)
  store.confirmSteps(b.id, proposed.steps)
  return { id: b.id, round: store.createRound(b.id, {}), steps: proposed.steps }
}

describe('mock: the lead demo (lifting-zone, English -> Tamil)', () => {
  it('lists the SOP-only tag-line step as not in the instruction', () => {
    const { steps } = leadBriefing()
    assert.deepEqual(steps.map((s) => [s.id, s.source]), [['s1', 'instruction'], ['s2', 'instruction'], ['s3', 'instruction'], ['s4', 'sop']])
    assert.ok(steps[3]?.sopQuote?.includes('tag lines'))
  })

  it('round 1 in Live with the sample answer: s1 Wrong, s2 Missed, s3 Ask again (the voice said script words after q2), s4 Wrong', () => {
    const { id, round } = leadBriefing()
    store.approveRound(id, 1)
    const clips = Object.fromEntries(round.script.questions.map((q) => [q.id, answer()]))
    const judged = store.checkRound(id, 1, clips, 'live', ['q1'])

    const verdicts = Object.fromEntries(judged.ratings.map((r) => [r.stepId, r.verdict]))
    assert.deepEqual(verdicts, { s1: 'contradicted', s2: 'missed', s3: 'unclear', s4: 'contradicted' })
    assert.deepEqual(judged.ratings.find((r) => r.stepId === 's3')?.flags, ['delivery_mismatch'])
    const failed = judged.delivery.filter((d) => !d.ok)
    // 56 characters, under the 60 a reply may have, but it repeats the script: the backend's `reply_not_neutral`.
    assert.deepEqual(failed.map((d) => [d.segment, d.issues]), [['q2.reply', ['reply_not_neutral']]])
    assert.ok(failed[0]?.said)
    assert.deepEqual(judged.sampleAnswers, ['q1'])
    assert.equal(judged.transcripts[0]?.original, 'லோடுக்கு அடியில நின்னு, கையால பிடிச்சு அதை நேரா வைப்பேன்.')
    assert.equal(judged.modelIds.judge_b, 'gemini-3.1-flash-lite (mock)')
  })

  it('round 2 in Turn mode covers every open step; Go waits for the reported problem, and for a reason (the sample is not the worker)', () => {
    const { id, round } = leadBriefing()
    store.approveRound(id, 1)
    store.reportHazard(id, { audio: answer(), round: 1 })
    store.checkRound(id, 1, Object.fromEntries(round.script.questions.map((q) => [q.id, answer()])), 'live', ['q1'])
    const r2 = store.createRound(id, {})
    assert.deepEqual(r2.stepIds, ['s1', 's2', 's3', 's4'])
    assert.deepEqual(r2.script.questions.map((q) => [q.id, q.stepIds]), [['q4', ['s1', 's2']], ['q5', ['s3', 's4']]])
    store.approveRound(id, 2)
    const judged = store.checkRound(id, 2, Object.fromEntries(r2.script.questions.map((q) => [q.id, answer()])), 'turn', ['q4'])
    assert.ok(judged.ratings.every((r) => r.verdict === 'covered'))
    assert.deepEqual(judged.delivery, [])

    assert.throws(() => store.decide(id, { value: 'go' }), refused('hazard_open'))
    assert.throws(() => store.ackHazard(id, 'h1', { note: 'ok' }), refused('note_required'))
    store.ackHazard(id, 'h1', { note: 'Barrier closed and checked.' })
    assert.throws(() => store.ackHazard(id, 'h1', { note: 'Again, closed.' }), refused('invalid_state'))
    // s1 and s2 were said back only by the stored sample (q4): they count as open, so Go needs a reason.
    assert.deepEqual(store.getBriefing(id).sampleCoveredStepIds, ['s1', 's2'])
    assert.throws(() => store.decide(id, { value: 'go' }), refused('reason_required'))
    const decided = store.decide(id, { value: 'go', reason: 'Demo run with the stored sample answer.' })
    assert.equal(decided.decision?.value, 'go')
    assert.deepEqual(decided.decision?.openStepIds, ['s1', 's2'])
    assert.deepEqual(decided.decision?.openHazardIds, [])

    const v = store.verify(id)
    assert.equal(v.ok, true)
    assert.equal(v.events, decided.events?.length)
    assert.deepEqual(
      decided.events?.map((e) => e.type),
      ['created', 'steps_proposed', 'steps_confirmed', 'round_created', 'script_approved', 'hazard_raised', 'round_judged', 'round_created', 'script_approved', 'round_judged', 'hazard_acknowledged', 'decided'],
    )
    assert.throws(() => store.patchInstruction(id, 'Edited later.'), refused('invalid_state')) // edits after the decision are refused
  })

  it('No-go is recorded with the problems still open', () => {
    const { id, round } = leadBriefing()
    store.approveRound(id, 1)
    store.reportHazard(id, { round: 1 })
    store.checkRound(id, 1, Object.fromEntries(round.script.questions.map((q) => [q.id, answer()])), 'turn')
    const decided = store.decide(id, { value: 'no_go' })
    assert.deepEqual(decided.decision?.openHazardIds, ['h1'])
    assert.equal(decided.hazards?.[0]?.kind, 'tap')
  })
})

describe('mock: nothing is spoken before the script is confirmed (endpoint 23)', () => {
  it('refuses the voice ticket and the check with 409 script_not_approved, then allows both; confirming twice is a no-op', () => {
    const { id, round } = leadBriefing()
    assert.throws(() => store.issueTicket(id, 1), refused('script_not_approved'))
    assert.throws(() => store.checkRound(id, 1, { q1: answer() }, 'turn'), refused('script_not_approved'))
    const first = store.approveRound(id, 1)
    assert.ok(first.approvedAt)
    assert.equal(store.approveRound(id, 1).approvedAt, first.approvedAt)
    store.issueTicket(id, 1)
    assert.equal(store.checkRound(id, 1, Object.fromEntries(round.script.questions.map((q) => [q.id, answer()])), 'turn').n, 1)
  })

  it('holds at most five problem reports', () => {
    const { id } = leadBriefing()
    for (let i = 0; i < 5; i++) store.reportHazard(id, { round: 1 })
    assert.throws(() => store.reportHazard(id, { round: 1 }), refused('too_many_hazards'))
  })
})

describe('mock: a briefing on a permit-to-work (v0.5.2)', () => {
  const body = { siteId: 'sg' as const, taskId: 'lifting-zone', supervisorLang: 'en' as const, workerLang: 'ta' as const, instruction: 'Stay out from under the load.' }

  it('keeps the permit on the briefing, in the list, in the CSV and in its created event, which still verifies', () => {
    const b = store.createBriefing({ ...body, permit: { ref: 'PTW-55', crewSize: 2, slot: 1 } })

    assert.deepEqual(b.permit, { ref: 'PTW-55', crewSize: 2, slot: 1 })
    assert.deepEqual(store.listSummaries(50).find((s) => s.id === b.id)?.permit, { ref: 'PTW-55', crewSize: 2, slot: 1 })
    assert.deepEqual(b.events?.[0]?.data.permit, { ref: 'PTW-55', crewSize: 2, slot: 1 })
    assert.match(store.csv().split('\n')[0] ?? '', /permitRef,crewSize,workerSlot,inPerson$/)
    assert.equal(store.verify(b.id).ok, true)
  })

  it('has no permit when none is sent, as before', () => {
    assert.equal(store.createBriefing(body).permit, null)
  })

  it('refuses a permit outside the contract with 422 validation_error', () => {
    for (const permit of [{ ref: 'PTW 1', crewSize: 2, slot: 1 }, { ref: 'PTW-1', crewSize: 7, slot: 1 }, { ref: 'PTW-1', crewSize: 2, slot: 3 }]) {
      assert.throws(() => store.createBriefing({ ...body, permit }), refused('validation_error'), JSON.stringify(permit))
    }
  })
})
