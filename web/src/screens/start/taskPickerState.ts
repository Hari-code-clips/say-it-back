// When the Start screen's task list is open, as data (no React), so the rules are unit-tested. The list starts collapsed to the chosen task
// so the permit block is on the first screen of a phone; every task stays one tap (or one key) away.

export type TaskListEvent =
  /** The `Change task` row was pressed. */
  | 'toggle'
  /** A task was picked with a tap, a click, Space or Enter: the choice is made, so the list closes. */
  | 'pick'
  /** An arrow key moved the selection: the user is still looking, so the list stays open. */
  | 'arrow'
  /** Escape. */
  | 'escape'

export function nextOpen(open: boolean, event: TaskListEvent): boolean {
  switch (event) {
    case 'toggle':
      return !open
    case 'pick':
    case 'escape':
      return false
    case 'arrow':
      return open
  }
}

// 17 Oct demo suites (build-notes/37-domain-suites.md): the open list shows one heading per work domain (catalog `domain`).

/** The UI string of each catalog domain; a domain this build does not know is headed by its own id. */
export const DOMAIN_KEYS = {
  construction: 'domain.construction',
  utilities: 'domain.utilities',
  marine: 'domain.marine',
  process: 'domain.process',
  manufacturing: 'domain.manufacturing',
  telecom: 'domain.telecom',
} as const

export const domainKey = (domain: string): (typeof DOMAIN_KEYS)[keyof typeof DOMAIN_KEYS] | undefined =>
  Object.hasOwn(DOMAIN_KEYS, domain) ? DOMAIN_KEYS[domain as keyof typeof DOMAIN_KEYS] : undefined

export interface Group<T> {
  /** The heading over the group, or undefined for options that name none. */
  heading: string | undefined
  items: T[]
}

/**
 * Options grouped under their headings, in the order each heading first appears, each group's options in their own order. The
 * catalog keeps a domain's tasks apart (fragile-roof, construction, comes after confined-space, utilities), so this is not a run
 * split: every domain gets one heading. With no heading anywhere the result is one group, the list as it was.
 */
export function groupByHeading<T extends { group?: string }>(items: readonly T[]): Group<T>[] {
  const groups: Group<T>[] = []
  for (const item of items) {
    const found = groups.find((g) => g.heading === item.group)
    if (found) found.items.push(item)
    else groups.push({ heading: item.group, items: [item] })
  }
  return groups
}
