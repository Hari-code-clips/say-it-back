import type { Briefing, BriefingSummary, CreateBriefingBody, CreateRoundBody, DecisionBody, Round, Step, Verdict } from '../api/types.ts'
import { publicCatalog, rawTask } from './catalog.ts'
import { judgeRound } from './judge.ts'
import { makeScript, proposeSteps } from './script.ts'
import { HttpError, newBriefingId, nowIso } from './util.ts'

// The mock backend's state machine (docs/API.md): the same rules, the same 409 / 422 errors.
// State lives in sessionStorage so a reload keeps the briefings, like the real store would.

const KEY = 'sib.mock.v1'
const MAX_ROUNDS = 3
const MAX_TICKETS_PER_ROUND = 2

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

function put(b: Briefing): Briefing {
  const next = { ...b, updatedAt: nowIso() }
  briefings = briefings.map((x) => (x.id === b.id ? next : x))
  persist()
  return next
}

const invalidState = (): HttpError => new HttpError(409, 'invalid_state', 'This action is not allowed in the briefing\'s current state.')

export function getBriefing(id: string): Briefing {
  const b = briefings.find((x) => x.id === id)
  if (!b) throw new HttpError(404, 'not_found', 'No such briefing.')
  return b
}

const openStepIds = (b: Briefing): string[] => b.steps.filter((s) => b.latestVerdicts[s.id] !== 'covered').map((s) => s.id)

export function createBriefing(body: CreateBriefingBody): Briefing {
  const site = publicCatalog.sites.find((s) => s.id === body.siteId)
  if (!site) throw new HttpError(422, 'invalid_site', 'Unknown site.')
  if (!site.supervisorLanguages.includes(body.supervisorLang) || !site.workerLanguages.includes(body.workerLang)) {
    throw new HttpError(422, 'invalid_language', 'That language pair is not offered at this site.')
  }
  const instruction = body.instruction.trim()
  if (!instruction || instruction.length > 1000) throw new HttpError(422, 'invalid_instruction', 'The instruction must be 1 to 1,000 characters.')
  let sop: Briefing['sop']
  if (body.taskId === 'custom') {
    if (!body.sop?.title.trim() || !body.sop.text.trim() || body.sop.text.length > 8000) throw new HttpError(422, 'invalid_sop', 'A custom SOP needs a title and text (up to 8,000 characters).')
    sop = { id: 'CUSTOM', version: 'v1', title: body.sop.title.trim(), text: body.sop.text.trim() }
  } else {
    const task = rawTask(body.taskId)
    if (!task) throw new HttpError(422, 'invalid_task', 'Unknown task.')
    sop = task.sop
  }
  const at = nowIso()
  const b: Briefing = {
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
    promptVersion: 'mock-2026-10-13',
    createdAt: at,
    updatedAt: at,
  }
  briefings = [b, ...briefings]
  persist()
  return b
}

export function patchInstruction(id: string, instruction: string): Briefing {
  const b = getBriefing(id)
  if (b.status !== 'draft' && b.status !== 'steps_proposed') throw invalidState()
  const text = instruction.trim()
  if (!text || text.length > 1000) throw new HttpError(422, 'invalid_instruction', 'The instruction must be 1 to 1,000 characters.')
  return put({ ...b, instruction: text })
}

export function extractSteps(id: string): Briefing {
  const b = getBriefing(id)
  if (b.status !== 'draft' && b.status !== 'steps_proposed') throw invalidState()
  const { steps, conflicts } = proposeSteps(b)
  return put({ ...b, steps, conflicts, status: 'steps_proposed' })
}

export function confirmSteps(id: string, steps: Step[]): Briefing {
  const b = getBriefing(id)
  if ((b.status !== 'steps_proposed' && b.status !== 'steps_confirmed') || b.rounds.length > 0) throw invalidState()
  const ids = new Set(steps.map((s) => s.id))
  if (steps.length < 1 || steps.length > 6 || ids.size !== steps.length || steps.some((s) => !s.text.trim())) {
    throw new HttpError(422, 'invalid_steps', 'Send 1 to 6 steps with unique ids and non-empty text.')
  }
  return put({ ...b, steps, stepsVersion: b.stepsVersion + 1, status: 'steps_confirmed' })
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
    if (b.rounds.length >= MAX_ROUNDS) throw new HttpError(409, 'max_rounds', 'Three rounds is the limit. Verify the open steps by demonstration.')
    const open = openStepIds(b)
    stepIds = body.stepIds?.length ? body.stepIds.filter((s) => open.includes(s)) : open
    if (stepIds.length === 0) throw new HttpError(422, 'invalid_steps', 'No open steps were selected.')
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
    modelIds: { script: 'gemini-3.8-flash (mock)', backTranslate: 'gemini-3.8-flash (mock)' },
    timingsMs: { script: 2400, backTranslate: 1700 },
    createdAt: nowIso(),
  }
  put({ ...b, rounds: [...b.rounds, round], status: 'briefing' })
  return round
}

export function getRound(id: string, n: number): Round {
  const round = getBriefing(id).rounds[n - 1]
  if (!round) throw new HttpError(404, 'not_found', 'No such round.')
  return round
}

/** Endpoint 11: counts tickets per round (at most 2). */
export function issueTicket(id: string, n: number): void {
  const b = getBriefing(id)
  const round = getRound(id, n)
  if (b.status !== 'briefing' || round.judgedAt) throw invalidState()
  const key = `${id}:${n}`
  const used = tickets.get(key) ?? 0
  if (used >= MAX_TICKETS_PER_ROUND) throw new HttpError(429, 'limit', 'At most 2 live sessions per round.')
  tickets.set(key, used + 1)
}

export function checkRound(id: string, n: number, clips: Record<string, Blob>, mode: 'live' | 'turn'): Round {
  const b = getBriefing(id)
  const round = getRound(id, n)
  if (b.status !== 'briefing' || round.judgedAt) throw invalidState()
  if (Object.keys(clips).length > 3) throw new HttpError(413, 'too_many_files', 'At most 3 files per check.')
  const judged = judgeRound({ briefing: b, round, clips, mode })
  const latestVerdicts: Record<string, Verdict> = { ...b.latestVerdicts }
  for (const r of judged.ratings) latestVerdicts[r.stepId] = r.verdict
  put({ ...b, rounds: b.rounds.map((r) => (r.n === n ? judged : r)), latestVerdicts, status: 'judged' })
  return judged
}

export function decide(id: string, body: DecisionBody): Briefing {
  const b = getBriefing(id)
  const explicitNoGo = body.value === 'no_go' && (b.status === 'steps_confirmed' || b.status === 'briefing')
  if (b.status !== 'judged' && !explicitNoGo) throw invalidState()
  if (body.value !== 'go' && body.value !== 'no_go') throw new HttpError(422, 'invalid_decision', 'The decision must be go or no_go.')
  const open = openStepIds(b)
  if (body.value === 'go' && open.length > 0 && (body.reason?.trim().length ?? 0) < 5) {
    throw new HttpError(422, 'reason_required', 'Going ahead with open steps needs a reason of at least 5 characters.')
  }
  return put({
    ...b,
    status: 'decided',
    decision: {
      value: body.value,
      ...(body.reason?.trim() ? { reason: body.reason.trim() } : {}),
      ...(body.by?.trim() ? { by: body.by.trim() } : {}),
      openStepIds: open,
      at: nowIso(),
    },
  })
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
  ]
  const rows = briefings.flatMap((b) =>
    b.steps.map((s) =>
      [
        b.id, b.createdAt, b.siteId, b.taskId, b.sop.id, b.sop.version, b.supervisorLang, b.workerLang,
        s.id, s.text, s.source, b.latestVerdicts[s.id] ?? '', b.rounds.length,
        b.decision?.value ?? '', b.decision?.reason ?? '', b.decision?.by ?? '', b.decision?.at ?? '',
      ].map(csvCell).join(','),
    ),
  )
  return [header.join(','), ...rows].join('\n') + '\n'
}
