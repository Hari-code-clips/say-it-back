import { useSyncExternalStore } from 'react'
import { CUSTOM_TASK_ID } from '../api/customTask.ts'
import type { Briefing, Catalog, Lang, SiteId, SopRef } from '../api/types.ts'
import { nextOnPermit, permitLink } from '../lib/permit.ts'

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
  /** v0.5.2: the permit-to-work block as typed (the ref may be incomplete); null or absent = not for a permit. */
  permit?: { ref: string; crewSize: number; slot: number } | null
  /** Library (16 Oct): the signed-off library version to start from; null or absent = the catalog or pasted SOP. */
  sopRef?: SopRef | null
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

/**
 * The first task (the lead demo) with its demo site and language pair, so "keep the defaults" runs the lead. A pair the site does
 * not offer falls back to the site's own defaults.
 */
export function defaultDraft(catalog: Catalog): Draft {
  const task = catalog.tasks[0]
  const site = catalog.sites.find((s) => s.id === task?.demoSite) ?? catalog.sites[0]
  const pair = task?.demoPair
  const supervisorLang = pair && site?.supervisorLanguages.includes(pair.supervisorLang) ? pair.supervisorLang : (site?.defaultSupervisorLanguage ?? 'en')
  const workerLang = pair && site?.workerLanguages.includes(pair.workerLang) ? pair.workerLang : (site?.defaultWorkerLanguage ?? 'ta')
  return {
    siteId: site?.id ?? 'sg',
    taskId: task?.id ?? CUSTOM_TASK_ID,
    supervisorLang,
    workerLang,
    customTitle: '',
    customSop: '',
    instruction: '',
    permit: null,
  }
}

/**
 * 17 Oct: picking a catalogue task also picks its demo site and language pair (each demo suite's stored answers exist only
 * there), when that site offers the pair; a task with no demo, or your own procedure, keeps the site and languages chosen.
 */
export function taskPatch(catalog: Catalog, taskId: string): Partial<Draft> {
  const task = catalog.tasks.find((t) => t.id === taskId)
  const site = catalog.sites.find((s) => s.id === task?.demoSite)
  const pair = task?.demoPair
  if (!site || !pair || !site.supervisorLanguages.includes(pair.supervisorLang) || !site.workerLanguages.includes(pair.workerLang)) {
    return { taskId, sopRef: null }
  }
  return { taskId, sopRef: null, siteId: site.id, supervisorLang: pair.supervisorLang, workerLang: pair.workerLang }
}

export const CUSTOM_TITLE_MIN = 2
export const CUSTOM_SOP_MIN = 20
export const CUSTOM_SOP_MAX = 8000
export const INSTRUCTION_MAX = 1000

export const customSopValid = (d: Draft): boolean =>
  d.taskId !== CUSTOM_TASK_ID || (d.customTitle.trim().length >= CUSTOM_TITLE_MIN && d.customSop.trim().length >= CUSTOM_SOP_MIN)

/** No permit, or one the contract takes (docs/API.md, "Permit-to-work grouping"). */
export const permitDraftValid = (d: Draft): boolean => !d.permit || permitLink(d.permit) !== null

/**
 * The next worker on `b`'s permit: the same site, task (and pasted SOP), languages and permit, the next slot, and the
 * previous instruction to start from. Null when `b` has no permit or was its last worker. No worker name is carried.
 */
export function nextWorkerDraft(b: Pick<Briefing, 'siteId' | 'taskId' | 'supervisorLang' | 'workerLang' | 'instruction' | 'sop' | 'permit'>): Draft | null {
  const next = b.permit ? nextOnPermit(b.permit) : null
  if (!next) return null
  const custom = b.taskId === CUSTOM_TASK_ID
  return {
    siteId: b.siteId,
    taskId: b.taskId,
    supervisorLang: b.supervisorLang,
    workerLang: b.workerLang,
    customTitle: custom ? b.sop.title : '',
    customSop: custom ? b.sop.text : '',
    instruction: b.instruction,
    permit: next,
  }
}
