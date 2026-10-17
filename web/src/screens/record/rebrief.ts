import { CUSTOM_TASK_ID } from '../../api/customTask.ts'
import type { Briefing } from '../../api/types.ts'
import type { Draft } from '../../flow/draft.ts'
import { nextOnPermit } from '../../lib/permit.ts'

// What the record offers next. With a permit: the next worker, or the same worker again after a No-go. A re-brief is a new
// briefing with the same permit and the same `slot`: docs/API.md, "Permit-to-work grouping" says a later post for a slot
// replaces it, so this needs no API change. Pure functions, no React.

type Permitted = Pick<Briefing, 'siteId' | 'taskId' | 'supervisorLang' | 'workerLang' | 'instruction' | 'sop' | 'permit'>

/**
 * A draft for the same worker on the same permit again: same site, task (and pasted SOP), languages, permit and slot, with the
 * previous instruction to start from. Null when the briefing is not on a permit. No worker name is carried (Rule 6).
 */
export function rebriefDraft(b: Permitted): Draft | null {
  if (!b.permit) return null
  const custom = b.taskId === CUSTOM_TASK_ID
  return {
    siteId: b.siteId,
    taskId: b.taskId,
    supervisorLang: b.supervisorLang,
    workerLang: b.workerLang,
    customTitle: custom ? b.sop.title : '',
    customSop: custom ? b.sop.text : '',
    instruction: b.instruction,
    permit: { ref: b.permit.ref, crewSize: b.permit.crewSize, slot: b.permit.slot },
  }
}

export type RecordAction =
  | { kind: 'next'; slot: number; crew: number }
  | { kind: 'rebrief'; slot: number }
  | { kind: 'new' }
  | { kind: 'all' }

export interface RecordBar {
  primary: RecordAction
  secondary: RecordAction
}

/**
 * The record's sticky bar. No permit: a new briefing, or all records. On a permit: the next worker leads after a Go, and a
 * No-go offers the same worker again (primary when this was the last worker, so the permit never dead-ends; beside the next
 * worker otherwise).
 */
export function recordBar(b: Pick<Briefing, 'permit' | 'decision'>): RecordBar {
  const permit = b.permit
  const next = permit ? nextOnPermit(permit) : null
  const nextAction: RecordAction | null = next ? { kind: 'next', slot: next.slot, crew: next.crewSize } : null
  const noGo = b.decision?.value === 'no_go'
  if (permit && noGo) {
    const again: RecordAction = { kind: 'rebrief', slot: permit.slot }
    return nextAction ? { primary: nextAction, secondary: again } : { primary: again, secondary: { kind: 'new' } }
  }
  if (nextAction) return { primary: nextAction, secondary: { kind: 'new' } }
  return { primary: { kind: 'new' }, secondary: { kind: 'all' } }
}
