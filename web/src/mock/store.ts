import type {
  Briefing,
  BriefingSummary,
  ChainEventType,
  CreateBriefingBody,
  CreateRoundBody,
  DecisionBody,
  Hazard,
  Round,
  Step,
  Verdict,
  VerifyResult,
} from '../api/types.ts'
import { permitLink } from '../lib/permit.ts'
import { deriveSampleCovered } from '../lib/sampleCovered.ts'
import { publicCatalog, rawTask } from './catalog.ts'
import { digest, sha256Hex, verifyChain, withEvent } from './chain.ts'
import { demoFor } from './demos.ts'
import { judgeRound } from './judge.ts'
import { approvedSteps, briefingSop, requireSignedOffSteps } from './library.ts'
import { makeScript, proposeSteps } from './script.ts'
import { HttpError, newBriefingId, nowIso } from './util.ts'

// The mock backend's state machine (docs/API.md v0.4): the same rules, the same 409 / 422 errors, and a hash-chained record:
// every change appends its event in the same update (chain.ts). State lives in sessionStorage so a reload keeps the briefings,
// like the real store would. The key's version changed with v0.4, so records of an older mock are not read back.

const KEY = 'sib.mock.v2'
const MAX_ROUNDS = 3
const MAX_TICKETS_PER_ROUND = 2
const MAX_HAZARDS = 5
const NOTE_MIN = 5

function load(): Briefing[] {
  try {
    const raw = sessionStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as Briefing[]) : []
  } catch {
    return []
  }
}

let briefings: Briefing[] = load()
const tickets = new Map<string, number>()

function persist(): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(briefings))
  } catch {
    /* storage unavailable */
  }
}

/** Store the change and its chain event together, as the backend does in one atomic update. */
function put(b: Briefing, type: ChainEventType, data: Record<string, unknown>): Briefing {
  const at = nowIso()
  // v0.4 review: `sampleCoveredStepIds` is derived from the rounds on every write, read-only on the wire.
  const next = withEvent({ ...b, updatedAt: at, sampleCoveredStepIds: deriveSampleCovered(b) }, type, data, at)
  briefings = briefings.map((x) => (x.id === b.id ? next : x))
  persist()
  return next
}

const invalidState = (): HttpError => new HttpError(409, 'invalid_state', "This action is not allowed in the briefing's current state.")

export function getBriefing(id: string): Briefing {
  const b = briefings.find((x) => x.id === id)
  if (!b) throw new HttpError(404, 'not_found', 'No such briefing.')
  return b
}

const openStepIds = (b: Briefing): string[] => b.steps.filter((s) => b.latestVerdicts[s.id] !== 'covered').map((s) => s.id)
/** What the decision treats as open (v0.4 review): not covered, or covered only by a stored sample answer. Re-explain uses `openStepIds`. */
const decisionOpenIds = (b: Briefing): string[] => {
  const sample = new Set(deriveSampleCovered(b))
  return b.steps.filter((s) => b.latestVerdicts[s.id] !== 'covered' || sample.has(s.id)).map((s) => s.id)
}
const openHazardIds = (b: Briefing): string[] => (b.hazards ?? []).filter((h) => !h.ack).map((h) => h.id)

export function createBriefing(body: CreateBriefingBody): Briefing {
  const site = publicCatalog.sites.find((s) => s.id === body.siteId)
  if (!site) throw new HttpError(422, 'unknown_site', 'Unknown site.')
  const workerLangs = [...site.workerLanguages, ...(site.evaluatorLanguages ?? [])] // + English for evaluators (16 Oct breadth)
  if (!site.supervisorLanguages.includes(body.supervisorLang) || !workerLangs.includes(body.workerLang)) {
    throw new HttpError(422, 'unsupported_language', 'That language pair is not offered at this site.')
  }
  const instruction = body.instruction.trim()
  if (!instruction || instruction.length > 1000) throw new HttpError(422, 'too_long', 'The instruction must be 1 to 1,000 characters.')
  let sop: Briefing['sop']
  if (body.sopRef) {
    sop = briefingSop({ ...body, sopRef: body.sopRef }) // library (16 Oct): an approved version, checked as the backend does
  } else if (body.taskId === 'custom') {
    if (!body.sop?.title.trim() || !body.sop.text.trim() || body.sop.text.length > 8000) throw new HttpError(422, 'sop_required', 'A custom SOP needs a title and text (up to 8,000 characters).')
    sop = { id: 'CUSTOM', version: 'v1', title: body.sop.title.trim(), text: body.sop.text.trim() }
  } else {
    const task = rawTask(body.taskId)
    if (!task) throw new HttpError(422, 'unknown_task', 'Unknown task.')
    sop = task.sop
  }
  // v0.5.2: an optional permit-to-work, checked as the backend does; it cannot change after creation.
  const permit = body.permit === undefined || body.permit === null ? null : permitLink(body.permit)
  if (body.permit && !permit) throw new HttpError(422, 'validation_error', 'permit: ref is 1-32 of [A-Za-z0-9._/-], crewSize 1-6, slot 1..crewSize.')
  const at = nowIso()
  const b = withEvent(
    {
      id: newBriefingId(),
      siteId: body.siteId,
      taskId: body.taskId,
      sop,
      supervisorLang: body.supervisorLang,
      workerLang: body.workerLang,
      instruction,
      status: 'draft',
      steps: [],
      stepsVersion: 0,
      conflicts: [],
      rounds: [],
      latestVerdicts: {},
      hazards: [],
      events: [],
      recordHash: '',
      sampleCoveredStepIds: [],
      permit,
      ...(body.sopRef ? { sopRef: body.sopRef } : {}),
      promptVersion: 'mock-2026-10-14',
      createdAt: at,
      updatedAt: at,
    },
    'created',
    { instructionSha256: sha256Hex(instruction), permit, ...(body.sopRef ? { sopRef: body.sopRef } : {}) },
    at,
  )
  briefings = [b, ...briefings]
  persist()
  return b
}

export function patchInstruction(id: string, instruction: string): Briefing {
  const b = getBriefing(id)
  if (b.status !== 'draft' && b.status !== 'steps_proposed') throw invalidState()
  const text = instruction.trim()
  if (!text || text.length > 1000) throw new HttpError(422, 'too_long', 'The instruction must be 1 to 1,000 characters.')
  return put({ ...b, instruction: text }, 'instruction_edited', { instructionSha256: sha256Hex(text) })
}

export function extractSteps(id: string): Briefing {
  const b = getBriefing(id)
  if (b.status !== 'draft' && b.status !== 'steps_proposed') throw invalidState()
  // Library (16 Oct): a library briefing proposes the version's approved steps, with no model call.
  const { steps, conflicts } = b.sopRef ? { steps: approvedSteps(b.siteId, b.sopRef), conflicts: [] } : proposeSteps(b)
  return put({ ...b, steps, conflicts, status: 'steps_proposed' }, 'steps_proposed', { stepIds: steps.map((s) => s.id) })
}

export function confirmSteps(id: string, steps: Step[]): Briefing {
  const b = getBriefing(id)
  if ((b.status !== 'steps_proposed' && b.status !== 'steps_confirmed') || b.rounds.length > 0) throw invalidState()
  const ids = new Set(steps.map((s) => s.id))
  if (steps.length < 1 || steps.length > 6 || ids.size !== steps.length || steps.some((s) => !s.text.trim())) {
    throw new HttpError(422, 'invalid_steps', 'Send 1 to 6 steps with unique ids and non-empty text.')
  }
  if (b.sopRef) requireSignedOffSteps({ ...b, sopRef: b.sopRef }, steps) // security fixes A (H2): signed-off steps as they are
  const stepsVersion = b.stepsVersion + 1
  return put({ ...b, steps, stepsVersion, status: 'steps_confirmed' }, 'steps_confirmed', { stepsVersion, stepsSha256: digest(steps) })
}

export function createRound(id: string, body: CreateRoundBody): Round {
  const b = getBriefing(id)
  const first = b.rounds.length === 0
  let stepIds: string[]
  if (first) {
    if (b.status !== 'steps_confirmed') throw invalidState()
    stepIds = b.steps.map((s) => s.id)
  } else {
    if (b.status !== 'judged' || openStepIds(b).length === 0) throw invalidState()
    if (b.rounds.length >= MAX_ROUNDS) throw new HttpError(409, 'invalid_state', 'Three rounds is the limit. Verify the open steps by demonstration.')
    const open = openStepIds(b)
    stepIds = body.stepIds?.length ? body.stepIds.filter((s) => open.includes(s)) : open
    if (stepIds.length === 0) throw new HttpError(422, 'invalid_step_ids', 'No open steps were selected.')
  }
  const questionsSoFar = b.rounds.reduce((n, r) => n + r.script.questions.length, 0)
  const n = b.rounds.length + 1
  const round: Round = {
    n,
    kind: first ? 'initial' : 'reexplain',
    stepIds,
    ...(body.supervisorNote?.trim() ? { supervisorNote: body.supervisorNote.trim() } : {}),
    script: makeScript(b, stepIds, questionsSoFar + 1),
    transcripts: [],
    passA: [],
    passB: [],
    ratings: [],
    delivery: [],
    nextAction: 'reexplain',
    modelIds: { script: 'gemini-3.8-flash (mock)', back_translate: 'gemini-3.8-flash (mock)', ...(first ? {} : { re_explain: 'gemini-3.8-flash (mock)' }) },
    timingsMs: { script: 2400, back_translate: 1700 },
    createdAt: nowIso(),
  }
  put({ ...b, rounds: [...b.rounds, round], status: 'briefing' }, 'round_created', { n, kind: round.kind, stepIds, scriptSha256: digest(round.script) })
  return round
}

export function getRound(id: string, n: number): Round {
  const round = getBriefing(id).rounds[n - 1]
  if (!round) throw new HttpError(404, 'round_not_found', 'No such round.')
  return round
}

/** v0.4 gate: nothing is spoken before the supervisor confirms the round's script (endpoint 23). */
export function requireApproved(id: string, n: number): Round {
  const round = getRound(id, n)
  if (!round.approvedAt) throw new HttpError(409, 'script_not_approved', "Confirm this round's script before the worker hears it.")
  return round
}

/** Endpoint 23. Approving twice is a no-op that returns the round. */
export function approveRound(id: string, n: number, by?: string): Round {
  const b = getBriefing(id)
  const round = getRound(id, n)
  if (b.status !== 'briefing' || round.judgedAt) throw invalidState()
  if (round.approvedAt) return round
  const approved: Round = { ...round, approvedAt: nowIso(), ...(by?.trim() ? { approvedBy: by.trim() } : {}) }
  put({ ...b, rounds: b.rounds.map((r) => (r.n === n ? approved : r)) }, 'script_approved', { n, scriptSha256: digest(round.script) })
  return approved
}

/** Endpoint 11: counts tickets per round (at most 2). */
export function issueTicket(id: string, n: number): void {
  const b = getBriefing(id)
  const round = getRound(id, n)
  if (b.status !== 'briefing' || round.judgedAt) throw invalidState()
  requireApproved(id, n)
  refuseDeclined(round)
  const key = `${id}:${n}`
  const used = tickets.get(key) ?? 0
  if (used >= MAX_TICKETS_PER_ROUND) throw new HttpError(429, 'limit', 'At most 2 live sessions per round.')
  tickets.set(key, used + 1)
}

export function checkRound(id: string, n: number, clips: Record<string, Blob>, mode: 'live' | 'turn', sampleAnswers: string[] = []): Round {
  const b = getBriefing(id)
  const round = getRound(id, n)
  if (b.status !== 'briefing' || round.judgedAt) throw invalidState()
  requireApproved(id, n)
  refuseDeclined(round)
  if (Object.keys(clips).length > 3) throw new HttpError(422, 'too_many_files', 'At most 3 files per check.')
  const judged = judgeRound({ briefing: b, round, clips, mode, sampleAnswers })
  const latestVerdicts: Record<string, Verdict> = { ...b.latestVerdicts }
  for (const r of judged.ratings) latestVerdicts[r.stepId] = r.verdict
  put({ ...b, rounds: b.rounds.map((r) => (r.n === n ? judged : r)), latestVerdicts, status: 'judged' }, 'round_judged', {
    n,
    mode,
    verdicts: Object.fromEntries(judged.ratings.map((r) => [r.stepId, r.verdict])),
    ratingsSha256: digest(judged.ratings),
    deliveryOk: judged.delivery.every((d) => d.ok),
    sampleAnswers: judged.sampleAnswers ?? [],
  })
  return judged
}

/** Endpoint 21: with audio, the mock "transcribes" the demo's report; without, it is a tap. */
export function reportHazard(id: string, { audio, round }: { audio?: Blob; round?: number }): Hazard {
  const b = getBriefing(id)
  if (b.status !== 'steps_confirmed' && b.status !== 'briefing' && b.status !== 'judged') throw invalidState()
  const hazards = b.hazards ?? []
  if (hazards.length >= MAX_HAZARDS) throw new HttpError(422, 'too_many_hazards', `At most ${MAX_HAZARDS} problem reports per briefing.`)
  if (audio && audio.size > 3 * 1024 * 1024) throw new HttpError(413, 'payload_too_large', 'The recording is over 3 MB.')
  const said = audio ? (demoFor(b)?.hazard ?? { original: `[mock] There is a problem here.`, translation: 'There is a problem here.' }) : undefined
  const hazard: Hazard = {
    id: `h${hazards.length + 1}`,
    ...(round ? { round } : {}),
    kind: audio ? 'voice' : 'tap',
    original: said?.original ?? '',
    translation: said?.translation ?? '',
    detectedLang: audio ? b.workerLang : 'none',
    raisedAt: nowIso(),
  }
  put({ ...b, hazards: [...hazards, hazard] }, 'hazard_raised', { hazardId: hazard.id, kind: hazard.kind })
  return hazard
}

/** Endpoint 22: what the supervisor did about it. */
export function ackHazard(id: string, hazardId: string, body: { note?: string; by?: string }): Briefing {
  const b = getBriefing(id)
  if (b.status !== 'steps_confirmed' && b.status !== 'briefing' && b.status !== 'judged') throw invalidState()
  const hazard = (b.hazards ?? []).find((h) => h.id === hazardId)
  if (!hazard) throw new HttpError(404, 'not_found', 'No such problem report.')
  if (hazard.ack) throw invalidState()
  const note = body.note?.trim() ?? ''
  if (note.length < NOTE_MIN) throw new HttpError(422, 'note_required', `Write what you did (at least ${NOTE_MIN} characters).`)
  const ack = { note, ...(body.by?.trim() ? { by: body.by.trim() } : {}), at: nowIso() }
  return put({ ...b, hazards: (b.hazards ?? []).map((h) => (h.id === hazardId ? { ...h, ack } : h)) }, 'hazard_acknowledged', {
    hazardId,
    kind: hazard.kind,
    noteSha256: sha256Hex(note),
  })
}

/** 2026-10-17, as the backend's state_machine.in_person_round: the latest round, while the worker's choice for it is a decline. */
function inPersonRound(b: Briefing): Round | undefined {
  const latest = b.rounds[b.rounds.length - 1]
  return b.status === 'briefing' && latest?.consent?.given === false ? latest : undefined
}

export function decide(id: string, body: DecisionBody): Briefing {
  const b = getBriefing(id)
  const explicitNoGo = body.value === 'no_go' && (b.status === 'steps_confirmed' || b.status === 'briefing')
  // 2026-10-17: a Go after the worker declined the recording is an in-person check (no model call, nothing heard).
  const inPerson = body.value === 'go' ? inPersonRound(b) : undefined
  if (b.status !== 'judged' && !explicitNoGo && !inPerson) throw invalidState()
  if (body.value !== 'go' && body.value !== 'no_go') throw new HttpError(422, 'validation_error', 'The decision must be go or no_go.')
  const scope = new Set([...decisionOpenIds(b), ...(inPerson?.stepIds ?? [])])
  const open = inPerson ? b.steps.filter((s) => scope.has(s.id)).map((s) => s.id) : decisionOpenIds(b)
  const openHazards = openHazardIds(b)
  if (body.value === 'go' && openHazards.length > 0) throw new HttpError(409, 'hazard_open', 'A problem the worker reported is not acknowledged yet.')
  if (body.value === 'go' && (open.length > 0 || inPerson) && (body.reason?.trim().length ?? 0) < 5) {
    throw new HttpError(422, 'reason_required', 'Going ahead with open steps needs a reason of at least 5 characters.')
  }
  const reason = body.reason?.trim()
  const by = body.by?.trim()
  const decision = {
    value: body.value,
    ...(reason ? { reason } : {}),
    ...(by ? { by } : {}),
    openStepIds: open,
    openHazardIds: openHazards,
    at: nowIso(),
    ...(inPerson ? { inPerson: true } : {}),
  }
  return put({ ...b, status: 'decided', decision }, 'decided', {
    value: body.value,
    openStepIds: open,
    openHazardIds: openHazards,
    reasonSha256: reason ? sha256Hex(reason) : null,
    by: by ?? null,
    ...(inPerson ? { inPerson: true } : {}), // only then, as the backend: every other event keeps its shape
  })
}

/**
 * Endpoint 25. QA flag `sib.mock.tamper` = "1" checks a copy of the record with one step's text edited after the fact, so the
 * broken-chain warning can be seen; nothing stored changes.
 */
export function verify(id: string): VerifyResult {
  const b = getBriefing(id)
  let tamper = false
  try {
    tamper = localStorage.getItem('sib.mock.tamper') === '1'
  } catch {
    /* storage unavailable */
  }
  if (tamper && b.steps[0]) return verifyChain({ ...b, steps: [{ ...b.steps[0], text: `${b.steps[0].text} (edited)` }, ...b.steps.slice(1)] })
  return verifyChain(b)
}

export function listSummaries(limit: number): BriefingSummary[] {
  return [...briefings]
    .sort((a, c) => c.createdAt.localeCompare(a.createdAt))
    .slice(0, limit)
    .map((b) => {
      const task = rawTask(b.taskId)
      return {
        id: b.id,
        siteId: b.siteId,
        taskId: b.taskId,
        taskTitle: task ? task.title : b.sop.title,
        supervisorLang: b.supervisorLang,
        workerLang: b.workerLang,
        status: b.status,
        rounds: b.rounds.length,
        ...(b.decision ? { decision: b.decision } : {}),
        permit: b.permit ?? null,
        createdAt: b.createdAt,
      }
    })
}

const csvCell = (v: string | number | undefined): string => {
  const s = String(v ?? '')
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

/** Endpoint 15: one row per briefing x step, with the contract's columns. */
export function csv(): string {
  const header = [
    'briefingId', 'createdAt', 'siteId', 'taskId', 'sopId', 'sopVersion', 'supervisorLang', 'workerLang',
    'stepId', 'stepText', 'source', 'finalVerdict', 'rounds', 'decision', 'decisionReason', 'decidedBy', 'decidedAt',
    'permitRef', 'crewSize', 'workerSlot', // v0.5.2
    'inPerson', // 2026-10-17: true, false, or empty before a decision
  ]
  const rows = briefings.flatMap((b) =>
    b.steps.map((s) =>
      [
        b.id, b.createdAt, b.siteId, b.taskId, b.sop.id, b.sop.version, b.supervisorLang, b.workerLang,
        s.id, s.text, s.source, b.latestVerdicts[s.id] ?? '', b.rounds.length,
        b.decision?.value ?? '', b.decision?.reason ?? '', b.decision?.by ?? '', b.decision?.at ?? '',
        b.permit?.ref ?? '', b.permit?.crewSize ?? '', b.permit?.slot ?? '',
        b.decision ? String(b.decision.inPerson === true) : '',
      ].map(csvCell).join(','),
    ),
  )
  return [header.join(','), ...rows].join('\n') + '\n'
}

// Privacy (16 Oct), as the backend's consent.py and retention.py: the worker's choice per round, and deleting a record. ------------

const declined = (): HttpError => new HttpError(409, 'consent_declined', 'The worker chose not to be recorded for this round. Brief them in person.')

/** A declined round takes no audio at all: no check, no live ticket. */
function refuseDeclined(round: Round): void {
  if (round.consent && !round.consent.given) throw declined()
}

/** The worker's choice for round `n` ("I agree" or "Not now"), with its `consent` chain event; the same choice again is a no-op. */
export function recordConsent(id: string, n: number, given: boolean): Round {
  const b = getBriefing(id)
  const round = getRound(id, n)
  if (b.status !== 'briefing' || round.judgedAt) throw invalidState()
  requireApproved(id, n)
  if (round.consent?.given === given) return round
  const next: Round = { ...round, consent: { given, at: nowIso() } }
  put({ ...b, rounds: b.rounds.map((r) => (r.n === n ? next : r)) }, 'consent', { n, given })
  return next
}

const notAgreed = (): HttpError => new HttpError(409, 'consent_required', 'The worker has not agreed to be recorded for this round yet. Ask them first.')

/**
 * Endpoint 13, as the service runs it (SIB_REQUIRE_CONSENT=true; security fixes B): a round with no recorded choice is checked only
 * as all stored samples, every question listed in `sampleAnswers` with its clip, whatever else is sent.
 */
export function requireConsent(id: string, n: number, clipIds: readonly string[], sampleAnswers: readonly string[]): void {
  const round = getRound(id, n)
  refuseDeclined(round)
  const questions = round.script.questions
  const samplesOnly = questions.length > 0 && questions.every((q) => sampleAnswers.includes(q.id) && clipIds.includes(q.id))
  if (!round.consent && !samplesOnly) throw notAgreed()
}

/**
 * Endpoint 11, as the service runs it (SIB_REQUIRE_CONSENT=true; security fixes B): a round with no recorded choice gets a Live ticket
 * only for a session the request declares samples-only (`{samplesOnly: true}`). The round's own state is answered first, as there.
 */
export function requireTicketConsent(id: string, n: number, samplesOnly: boolean): void {
  const b = getBriefing(id)
  const round = getRound(id, n)
  if (b.status !== 'briefing' || round.judgedAt) throw invalidState()
  requireApproved(id, n)
  refuseDeclined(round)
  if (!round.consent && !samplesOnly) throw notAgreed()
}

/** DELETE /api/briefings/{id}: the record is removed at once. */
export function deleteBriefing(id: string): { ok: boolean; id: string } {
  getBriefing(id)
  briefings = briefings.filter((x) => x.id !== id)
  persist()
  return { ok: true, id }
}
