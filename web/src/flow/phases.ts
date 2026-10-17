import type { Briefing, Hazard, Round, Step } from '../api/types.ts'

// Screens of the briefing flow, and which of them the server-side state machine allows.
// (docs/API.md: draft -> steps_proposed -> steps_confirmed -> briefing -> judged -> ... -> decided)

export type Phase = 'instruction' | 'steps' | 'script' | 'brief' | 'result' | 'reexplain' | 'decision' | 'record'
/** Every screen of the flow, including Start, which runs before a briefing exists. */
export type FlowStep = Phase | 'start'

export const PHASES: readonly Phase[] = ['instruction', 'steps', 'script', 'brief', 'result', 'reexplain', 'decision', 'record']

export const isPhase = (value: string | undefined): value is Phase => PHASES.includes(value as Phase)

export const MAX_ROUNDS = 3

export function allowedPhases(b: Briefing): readonly Phase[] {
  switch (b.status) {
    case 'draft':
    case 'steps_proposed':
      return ['instruction', 'steps']
    case 'steps_confirmed':
      return ['steps']
    case 'briefing':
      // v0.4: the worker's screen opens only once the supervisor has confirmed this round's script (endpoint 23). A briefing
      // recovered with an unconfirmed round goes back to its script. 2026-10-17: after the worker declined the recording, the
      // supervisor records an in-person check on the decision screen.
      if (awaitsInPersonCheck(b)) return ['script', 'brief', 'decision']
      return latestRound(b)?.approvedAt || b.rounds.length === 0 ? ['script', 'brief'] : ['script']
    case 'judged':
      return ['result', 'reexplain', 'decision']
    case 'decided':
      return ['record']
  }
}

export function defaultPhase(b: Briefing): Phase {
  switch (b.status) {
    case 'draft':
    case 'steps_proposed':
    case 'steps_confirmed':
      return 'steps'
    case 'briefing':
      return 'script'
    case 'judged':
      return 'result'
    case 'decided':
      return 'record'
  }
}

/**
 * The named phases of the flow header (web/design.md): Steps, Script, Worker, Result, Decision. Rounds are the only count the
 * UI shows; there is no "step N of M", so a second round never makes the progress go backwards.
 */
export const PHASE_BAR = ['steps', 'script', 'worker', 'result', 'decision'] as const
export type BarPhase = (typeof PHASE_BAR)[number]

/** The named phase a screen belongs to. null: no bar (the Start form runs before a briefing exists). */
export const BAR_PHASE: Record<FlowStep, BarPhase | null> = {
  start: null,
  instruction: 'steps',
  steps: 'steps',
  script: 'script',
  brief: 'worker',
  result: 'result',
  reexplain: 'result',
  decision: 'decision',
  record: 'decision',
}

export type BarState = 'done' | 'current' | 'todo'

/** The five phases with where the screen is among them; empty for a screen with no bar. */
export function phaseBar(step: FlowStep): { phase: BarPhase; state: BarState }[] {
  const here = BAR_PHASE[step]
  if (!here) return []
  const at = PHASE_BAR.indexOf(here)
  return PHASE_BAR.map((phase, i) => ({ phase, state: i < at ? 'done' : i === at ? 'current' : 'todo' }))
}

export const latestRound = (b: Briefing): Round | undefined => b.rounds[b.rounds.length - 1]

/**
 * 2026-10-17 (docs/API.md Deviations, "in-person check after a decline"): the worker said "Not now" to the latest round's recording,
 * so nothing of it is heard or checked, and the supervisor checks them in person. A Go is then allowed before any check (endpoint 14),
 * always with a reason, every step of the round open, and the decision says `inPerson`.
 */
export const awaitsInPersonCheck = (b: Pick<Briefing, 'status' | 'rounds'>): boolean =>
  b.status === 'briefing' && b.rounds[b.rounds.length - 1]?.consent?.given === false

/** Steps whose latest rating is not `covered` (a step that was never rated counts as open). */
export function openSteps(b: Briefing): Step[] {
  return b.steps.filter((s) => b.latestVerdicts[s.id] !== 'covered')
}

export const canReexplain = (b: Briefing): boolean => b.status === 'judged' && b.rounds.length < MAX_ROUNDS && openSteps(b).length > 0

/** v0.4: problems the worker reported that the supervisor has not acknowledged yet. Each one locks Go. */
export const openHazards = (b: Pick<Briefing, 'hazards'>): Hazard[] => (b.hazards ?? []).filter((h) => !h.ack)
