import type { IconName } from '../theme/iconNames.ts'

// The catalog names each task's icon by an id of its own; this maps it to a Material Symbol (kept apart from catalog.tsx so
// tests/api/taskIcons.test.ts can check every catalog task against it).

export const TASK_ICONS: Readonly<Record<string, IconName>> = {
  electric: 'bolt',
  height: 'stairs',
  fire: 'local_fire_department',
  crane: 'precision_manufacturing',
  trench: 'plumbing',
  // v0.5 held-out eval tasks. Material Symbols has no manhole icon: the gas test is the first thing a confined-space entry needs.
  confined: 'gas_meter',
  roof: 'roofing',
  // 17 Oct demo suites (build-notes/37-domain-suites.md); each name checked against the Google Fonts subset API.
  jet: 'water_drop',
  steam: 'valve',
  press: 'compress',
  tower: 'cell_tower',
}

/** Catalog icon id -> Material Symbol; a generic one for an id this build does not know. */
export const taskIcon = (id: string | undefined): IconName => (id ? TASK_ICONS[id] : undefined) ?? 'construction'
