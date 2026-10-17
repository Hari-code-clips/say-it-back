import type { Catalog, CreateBriefingBody } from '../api/types.ts'
import { saveStartBriefing } from './startBriefing.ts'

// The 90-second judge demo (review P0-17, 17 Oct): one tap on the landing page starts the lead case and the handover opens with
// "Use stored sample answers" chosen, so an evaluator with no Tamil reaches the semantic result. Client only: the briefing is an
// ordinary one (same endpoints, mock and real API), and the supervisor's gates (confirm the steps, approve the script) stay.

/** The lead demo: Singapore, "Crane lift: the lifting zone", English to Tamil, the catalogue's sample instruction. */
export const JUDGE_DEMO_TASK = 'lifting-zone'

/** The create-briefing body of the lead case, or null when the catalogue has no such task, pair or sample instruction. */
export function judgeDemoBody(catalog: Catalog): CreateBriefingBody | null {
  const task = catalog.tasks.find((t) => t.id === JUDGE_DEMO_TASK)
  const site = catalog.sites.find((s) => s.id === task?.demoSite)
  if (!task || !site) return null
  const { supervisorLang, workerLang } = task.demoPair
  if (!site.supervisorLanguages.includes(supervisorLang) || !site.workerLanguages.includes(workerLang)) return null
  const instruction = task.sampleInstruction[supervisorLang]?.trim() // the supervisor's own words, never another language's
  if (!instruction) return null
  return { siteId: site.id, taskId: task.id, supervisorLang, workerLang, instruction }
}

// Which briefing the judge demo started, for this tab only (sessionStorage): its handovers open with the stored samples chosen.
const KEY = 'sib.judgeDemo'

export function markJudgeDemo(id: string): void {
  try {
    sessionStorage.setItem(KEY, id)
  } catch {
    /* storage unavailable: the handover opens unticked, as for any briefing */
  }
}

export function isJudgeDemo(id: string): boolean {
  try {
    return sessionStorage.getItem(KEY) === id
  } catch {
    return false
  }
}

export interface JudgeDemoIo {
  create: (body: CreateBriefingBody) => Promise<{ id: string }>
  patch: (id: string, instruction: string) => Promise<unknown>
  extract: (id: string) => Promise<unknown>
}

/**
 * Create the lead case's briefing (a Retry after a failed extract reuses it: `held` as in startBriefing.ts), mark it as the judge
 * demo's, and find its critical steps. Resolves to the Steps screen's path; throws what the failing call threw.
 */
export async function startJudgeDemo(lead: CreateBriefingBody, held: { id: string | null }, io: JudgeDemoIo): Promise<string> {
  const id = await saveStartBriefing(held, lead.instruction, { create: () => io.create(lead), patch: io.patch })
  markJudgeDemo(id)
  await io.extract(id)
  return `/b/${id}/steps`
}
