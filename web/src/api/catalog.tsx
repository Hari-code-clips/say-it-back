import { createContext, useContext, type ReactNode } from 'react'
import { useAsync, type AsyncState } from '../lib/useAsync.ts'
import type { IconName } from '../theme/iconNames.ts'
import { api } from './endpoints.ts'
import type { Catalog, CatalogTask, Lang } from './types.ts'

const CatalogContext = createContext<AsyncState<Catalog> | null>(null)

/** Loads GET /api/catalog once for the whole app. */
export function CatalogProvider({ children }: { children: ReactNode }) {
  const state = useAsync(() => api.catalog(), [])
  return <CatalogContext value={state}>{children}</CatalogContext>
}

export function useCatalog(): AsyncState<Catalog> {
  const v = useContext(CatalogContext)
  if (!v) throw new Error('CatalogProvider is missing')
  return v
}

/** Text for `lang`, falling back to English, then to any available language. */
export function pickText(value: string | Partial<Record<Lang, string>> | undefined, lang: Lang): string {
  if (!value) return ''
  if (typeof value === 'string') return value
  return value[lang] ?? value.en ?? Object.values(value)[0] ?? ''
}

const TASK_ICONS: Record<string, IconName> = {
  electric: 'bolt',
  height: 'stairs',
  fire: 'local_fire_department',
  crane: 'precision_manufacturing',
  trench: 'plumbing',
}

/** Catalog icon id -> Material Symbol. */
export const taskIcon = (id: string | undefined): IconName => (id ? TASK_ICONS[id] : undefined) ?? 'construction'

export const CUSTOM_TASK_ID = 'custom'

export function findTask(catalog: Catalog | undefined, id: string): CatalogTask | undefined {
  return catalog?.tasks.find((t) => t.id === id)
}

/** The catalog's example instruction for a task, in the supervisor's language when it has one. */
export function sampleInstructionFor(task: CatalogTask | undefined, lang: Lang): string {
  return pickText(task?.sampleInstruction, lang)
}

/** BCP-47 tag for `lang=` attributes, from the catalog when loaded. */
export function bcp47(catalog: Catalog | undefined, lang: Lang, siteId?: string): string {
  const site = catalog?.sites.find((s) => s.id === siteId)
  return site?.bcp47Overrides?.[lang] ?? catalog?.languages[lang]?.bcp47 ?? lang
}

/** The language's own name ("தமிழ்"), falling back to the code. */
export const langNative = (catalog: Catalog | undefined, lang: Lang): string => catalog?.languages[lang]?.native ?? lang
