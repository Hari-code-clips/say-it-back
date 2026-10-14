import { useSyncExternalStore } from 'react'
import { CUSTOM_TASK_ID } from '../api/catalog.tsx'
import type { Catalog, Lang, SiteId } from '../api/types.ts'

// The briefing being set up, before POST /api/briefings has created it (Start + Instruction).
// Kept in sessionStorage so a reload does not lose it; cleared once the briefing exists.

export interface Draft {
  siteId: SiteId
  taskId: string
  supervisorLang: Lang
  workerLang: Lang
  customTitle: string
  customSop: string
  instruction: string
}

const KEY = 'sib.draft'
const listeners = new Set<() => void>()

function load(): Draft | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as Draft) : null
  } catch {
    return null
  }
}

let state: Draft | null = load()

export function setDraft(next: Draft | null): void {
  state = next
  try {
    if (next) sessionStorage.setItem(KEY, JSON.stringify(next))
    else sessionStorage.removeItem(KEY)
  } catch {
    /* storage unavailable: the draft just lives in memory */
  }
  listeners.forEach((l) => l())
}

export function patchDraft(patch: Partial<Draft>): void {
  if (state) setDraft({ ...state, ...patch })
}

const subscribe = (cb: () => void) => {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

export const useDraft = (): Draft | null => useSyncExternalStore(subscribe, () => state)

/** First site, its default languages, first task. */
export function defaultDraft(catalog: Catalog): Draft {
  const site = catalog.sites[0]
  return {
    siteId: site?.id ?? 'sg',
    taskId: catalog.tasks[0]?.id ?? CUSTOM_TASK_ID,
    supervisorLang: site?.defaultSupervisorLanguage ?? 'en',
    workerLang: site?.defaultWorkerLanguage ?? 'ta',
    customTitle: '',
    customSop: '',
    instruction: '',
  }
}

export const CUSTOM_TITLE_MIN = 2
export const CUSTOM_SOP_MIN = 20
export const CUSTOM_SOP_MAX = 8000
export const INSTRUCTION_MAX = 1000

export const customSopValid = (d: Draft): boolean =>
  d.taskId !== CUSTOM_TASK_ID || (d.customTitle.trim().length >= CUSTOM_TITLE_MIN && d.customSop.trim().length >= CUSTOM_SOP_MIN)
