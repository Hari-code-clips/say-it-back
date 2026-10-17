import type { Lang, LibraryEntry, LibraryVersion, SopRef, Step } from '../../api/types.ts'

// Pure rules of the SOP library (docs/API.md Deviations 2026-10-16), shared by the screens and the mock backend.

export interface Offer {
  entry: LibraryEntry
  version: LibraryVersion
}

export const latestVersion = (entry: LibraryEntry): LibraryVersion | undefined => entry.versions[entry.versions.length - 1]

export const openDraft = (entry: LibraryEntry): LibraryVersion | undefined => entry.versions.find((v) => v.status === 'draft')

/**
 * Whether "New version" is offered: never while a draft is open, and (security fixes A, H3) never on a catalogue seed without
 * accounts, where the backend answers 403: a catalogue SOP id must not name steps an anonymous browser wrote.
 */
export const takesNewVersion = (entry: LibraryEntry, accounts: boolean): boolean => !openDraft(entry) && (accounts || !entry.seeded)

export const refOf = ({ entry, version }: Offer): SopRef => ({ sopId: entry.id, version: version.number })

export const sameRef = (a: SopRef | null | undefined, b: SopRef | null | undefined): boolean =>
  !!a && !!b && a.sopId === b.sopId && a.version === b.version

/**
 * What a supervisor may start a briefing from: the approved versions of this task's SOPs whose steps are in the supervisor's
 * language (the supervisor confirms them), newest first. Drafts are never offered.
 */
export function offeredVersions(entries: readonly LibraryEntry[], taskId: string, lang: Lang): Offer[] {
  return entries
    .filter((entry) => entry.taskId === taskId)
    .flatMap((entry) => entry.versions.filter((v) => v.status === 'approved' && v.lang === lang).map((version) => ({ entry, version })))
    .sort((a, b) => b.version.number - a.version.number)
}

/** The chosen version, if it is still on offer for this task and language; otherwise the Start screen falls back to the catalog SOP. */
export const stillOffered = (offers: readonly Offer[], ref: SopRef | null | undefined): SopRef | null =>
  offers.some((o) => sameRef(refOf(o), ref)) ? (ref ?? null) : null

/** A draft's steps as the server takes them: unique short ids in the order shown, trimmed, empty rows dropped. */
export const numbered = (steps: readonly Step[]): Step[] =>
  steps
    .filter((s) => s.text.trim())
    .map((s, i) => ({ ...s, id: `s${i + 1}`, text: s.text.trim(), hazard: s.hazard.trim(), speakable: s.speakable ?? true }))
