import { CUSTOM_TASK_ID } from '../../api/customTask.ts'
import { CUSTOM_SOP_MIN, CUSTOM_TITLE_MIN, type Draft } from '../../flow/draft.ts'
import type { StringKey } from '../../i18n/en.ts'
import { permitRefValid } from '../../lib/permit.ts'

// Why `Continue` is off on the Start screen, as data. A disabled button that says nothing is the fault the audit found
// (build-notes/25, F8); the screen shows `need` next to it. Checks run in the order the form is read.

export interface StartNeed {
  key: StringKey
  /** Values for the placeholders of `key`. */
  values?: Record<string, number>
}

export function startNeed(d: Draft): StartNeed | null {
  if (d.taskId === CUSTOM_TASK_ID) {
    if (d.customTitle.trim().length < CUSTOM_TITLE_MIN) return { key: 'start.need.customTitle' }
    if (d.customSop.trim().length < CUSTOM_SOP_MIN) return { key: 'start.need.customSop', values: { min: CUSTOM_SOP_MIN } }
  }
  const permit = d.permit
  if (permit) {
    if (!permit.ref.trim()) return { key: 'start.need.permitRef' }
    if (!permitRefValid(permit.ref)) return { key: 'start.need.permitRefInvalid' }
  }
  return null
}

/** The order of the Start screen's sections: the permit sits right under the task (permit-to-work is the product's positioning). */
export const START_SECTIONS = ['task', 'permit', 'site', 'languages'] as const
