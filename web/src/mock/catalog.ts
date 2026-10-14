import type { Catalog, CatalogTask, Lang, Step } from '../api/types.ts'
import raw from './catalog.json'

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
  tasks: rawTasks.map(({ id, icon, title, demoSite, demoPair, sop, sampleInstruction }) => ({
    id,
    icon,
    title,
    demoSite,
    demoPair,
    sop,
    sampleInstruction,
  })),
}

export const rawTask = (id: string): RawTask | undefined => rawTasks.find((t) => t.id === id)

export const langNameEn = (lang: Lang): string => full.languages[lang]?.name ?? lang
