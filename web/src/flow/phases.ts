import type { Briefing, Round, Step } from '../api/types.ts'

// Screens of the briefing flow, and which of them the server-side state machine allows.
// (docs/API.md: draft -> steps_proposed -> steps_confirmed -> briefing -> judged -> ... -> decided)

export type Phase = 'instruction' | 'steps' | 'script' | 'brief' | 'result' | 'reexplain' | 'decision' | 'record'
/** The progress indicator also covers the Start screen, which runs before a briefing exists. */
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
      return ['script', 'brief']
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

/** Position in the progress indicator. */
export const PROGRESS: Record<FlowStep, number> = {
  start: 1,
  instruction: 2,
  steps: 3,
  script: 4,
  brief: 5,
  result: 6,
  reexplain: 6,
  decision: 7,
  record: 7,
}
export const PROGRESS_TOTAL = 7

export const latestRound = (b: Briefing): Round | undefined => b.rounds[b.rounds.length - 1]

/** Steps whose latest rating is not `covered` (a step that was never rated counts as open). */
export function openSteps(b: Briefing): Step[] {
  return b.steps.filter((s) => b.latestVerdicts[s.id] !== 'covered')
}

export const canReexplain = (b: Briefing): boolean => b.status === 'judged' && b.rounds.length < MAX_ROUNDS && openSteps(b).length > 0
