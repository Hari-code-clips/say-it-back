// Who holds the phone, at each point of a briefing round (F1-F3 of build-notes/25), as plain data and functions so the rules are
// tested without a DOM. One route, `/b/:id/brief`, shows seven stages:
//
//   handover        supervisor   mode, sample answers, "Give phone to worker"
//   worker_ready    worker       one big Start
//   worker_running  worker       the voice session (orb, caption, Done)
//   worker_failed   worker       "Give the phone to your supervisor", and nothing else but the held "I'm the supervisor"
//   recovery        supervisor   the details of a failure and the way out
//   handback        in transit   the worker is told to give the phone back; the supervisor holds "Supervisor: hold to continue"
//   checking        supervisor   the check's wait; the result opens from here, never before

/** The run's own state (see useBriefingRun). */
export type RunKind = 'ready' | 'running' | 'failed' | 'submitting' | 'submit_failed'

export type Stage = 'handover' | 'worker_ready' | 'worker_running' | 'worker_failed' | 'recovery' | 'handback' | 'checking'

export interface StageInput {
  run: RunKind
  /** The supervisor pressed "Give phone to worker" (or sent the phone back to the worker to try again). */
  handed: boolean
  /** The supervisor held "I'm the supervisor" on a worker's failure screen. */
  tookOver: boolean
  /** The supervisor held "Supervisor: hold to continue" (1.5 s) after the worker's last answer. */
  haveThePhone: boolean
}

export function stageOf({ run, handed, tookOver, haveThePhone }: StageInput): Stage {
  switch (run) {
    case 'ready':
      return handed ? 'worker_ready' : 'handover'
    case 'running':
      return 'worker_running'
    case 'failed':
      // The details and the recovery actions are the supervisor's: they appear only after the supervisor takes over.
      return tookOver ? 'recovery' : 'worker_failed'
    case 'submitting':
      return haveThePhone ? 'checking' : 'handback'
    case 'submit_failed':
      // The worker has already finished and is holding the "give the phone back" screen. A failed check is for the supervisor.
      return haveThePhone ? 'recovery' : 'handback'
  }
}

/** Who is meant to be reading the screen. The hand-back screen is for the worker's last message and the supervisor's one tap. */
export type Holder = 'supervisor' | 'worker' | 'transit'

export const HOLDER: Record<Stage, Holder> = {
  handover: 'supervisor',
  worker_ready: 'worker',
  worker_running: 'worker',
  worker_failed: 'worker',
  recovery: 'supervisor',
  handback: 'transit',
  checking: 'supervisor',
}

/** A stage the worker holds the phone in: it shows worker-language text, icons, one action and the problem button. */
export const workerHolds = (stage: Stage): boolean => HOLDER[stage] === 'worker'

export interface GateInput {
  /** The check came back (the round is judged on the server). */
  judged: boolean
  /** The supervisor held "Supervisor: hold to continue". */
  haveThePhone: boolean
  /** A problem report of the worker's is still being recorded, sent, or failed and not deliberately deleted. */
  reportHolds: boolean
}

/**
 * The result opens when the check is done AND the supervisor has the phone AND no report is held. It never opens by itself on
 * the worker's phone: a check that finishes while the worker still holds it just waits behind the hand-back screen.
 */
export const resultMayOpen = ({ judged, haveThePhone, reportHolds }: GateInput): boolean => judged && haveThePhone && !reportHolds

/**
 * The elapsed seconds of the check's wait, counted from the moment the check request went out (not from the tap), so a
 * supervisor who takes the phone late still sees how long the check has really been running.
 */
export const secondsSince = (startedAt: number, now: number): number => Math.max(0, Math.floor((now - startedAt) / 1000))
