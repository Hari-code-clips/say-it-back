import type { Catalog, CatalogTask, Lang, Step } from '../api/types.ts'
import raw from './catalog.json' with { type: 'json' }

// A copy of backend/sayitback/data/catalog.json. The real GET /api/catalog strips
// referenceSteps, referenceQuestions and demoScripts; the mock needs them to play the backend.
// Re-copy the file when the backend catalog changes.

export interface RawTask extends CatalogTask {
  referenceSteps: Step[]
  referenceQuestions: { id: string; text: string; stepIds: string[] }[]
}

const full = raw as unknown as Catalog
const rawTasks = (raw as unknown as { tasks: RawTask[] }).tasks

/** What GET /api/catalog returns. */
export const publicCatalog: Catalog = {
  version: full.version,
  languages: full.languages,
  sites: full.sites,
  tasks: rawTasks.map(({ id, icon, domain, title, demoSite, demoPair, sop, sampleInstruction }) => ({
    id,
    icon,
    ...(domain ? { domain } : {}),
    title,
    demoSite,
    demoPair,
    sop,
    sampleInstruction,
  })),
}

export const rawTask = (id: string): RawTask | undefined => rawTasks.find((t) => t.id === id)

/** One scripted answer of a demo round: what the worker says to one reference question, and the verdicts it should get. */
export interface RawDemoAnswer {
  questionId: string
  answer: Partial<Record<Lang, string>>
  expected: Record<string, string>
}

/** The catalog's scripted demo answers (`demoScripts`): what a worker says in each round of a demo. */
export interface RawDemoScript {
  id: string
  taskId: string
  siteId: string
  supervisorLang: Lang
  workerLang: Lang
  /** Each round's own answer, and since 16 Oct its answers to the task's other questions (`followUps`). */
  rounds: (RawDemoAnswer & { followUps?: RawDemoAnswer[] })[]
}

export const rawDemoScripts = (raw as unknown as { demoScripts?: RawDemoScript[] }).demoScripts ?? []

export const rawDemoScript = (id: string): RawDemoScript | undefined => rawDemoScripts.find((d) => d.id === id)

/** A demo round's scripted answers: its own, then its follow-ups (the catalog lists them in reference question order). */
export const roundAnswers = (round: RawDemoScript['rounds'][number] | undefined): RawDemoAnswer[] => (round ? [round, ...(round.followUps ?? [])] : [])

export const langNameEn = (lang: Lang): string => full.languages[lang]?.name ?? lang
