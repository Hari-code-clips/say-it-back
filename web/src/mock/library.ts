import type { Briefing, CreateBriefingBody, Lang, LibraryEntry, LibraryVersion, SiteId, SopRef, Step } from '../api/types.ts'
import { openDraft } from '../screens/library/libraryModel.ts'
import { publicCatalog, rawTask } from './catalog.ts'
import { HttpError, nowIso } from './util.ts'

// The SOP library for dev:mock, as the backend serves it (sop_library.py): each catalog task is an approved, read-only seed of
// its demo site (the catalog SOP under its own number, its referenceSteps); new SOPs and their versions are this browser's own,
// kept in localStorage. A mock has one caller and no accounts, so there is no scope and no role, and (security fixes A, H3) a
// seed takes no new version: a catalogue SOP id never names steps this browser wrote.

export const CATALOGUE_READ_ONLY = 'Catalogue SOPs are read-only in this demo. Add your own SOP instead.'

const KEY = 'sib.mock.library'
let stored: LibraryEntry[] = load()

function load(): LibraryEntry[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '[]') as LibraryEntry[]
  } catch {
    return []
  }
}

function persist(): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(stored))
  } catch {
    /* storage unavailable: the library lives in memory */
  }
}

/** Test hook: forget this browser's versions. */
export function resetLibrary(): void {
  stored = []
  persist()
}

export function seeds(siteId: SiteId): LibraryEntry[] {
  const day = `${publicCatalog.version}T00:00:00.000Z`
  return publicCatalog.tasks
    .filter((t) => t.demoSite === siteId)
    .map((t) => {
      const task = rawTask(t.id)
      const version: LibraryVersion = {
        number: Number(t.sop.version.replace(/\D/g, '')) || 1,
        text: t.sop.text,
        lang: 'en',
        createdAt: day,
        createdBy: 'catalog',
        changeNote: 'From the demo catalog.',
        status: 'approved',
        // As the backend's Step model reads them: a catalog step without `speakable` is speakable.
        steps: (task?.referenceSteps ?? []).map((s) => ({ ...structuredClone(s), speakable: s.speakable ?? true })),
        approvedBy: 'catalog',
        approvedAt: day,
        readOnly: true,
      }
      return { id: t.sop.id, siteId, title: t.sop.title, taskId: t.id, seeded: true, versions: [version] }
    })
}

function site(siteId: string): SiteId {
  if (!publicCatalog.sites.some((s) => s.id === siteId)) throw new HttpError(404, 'unknown_site', 'Unknown site.')
  return siteId as SiteId
}

export function listSops(siteId: string): LibraryEntry[] {
  const id = site(siteId)
  const entries = seeds(id)
  for (const own of stored.filter((e) => e.siteId === id)) {
    const seed = entries.find((e) => e.id === own.id)
    if (seed) seed.versions.push(...structuredClone(own.versions))
    else entries.push(structuredClone(own))
  }
  return entries
}

function entryOf(siteId: string, sopId: string): LibraryEntry {
  const found = listSops(siteId).find((e) => e.id === sopId)
  if (!found) throw new HttpError(404, 'sop_not_found', 'SOP not found.')
  return found
}

/** Keep `entry` as this browser's: a seed keeps only its later versions. */
function save(entry: LibraryEntry): LibraryEntry {
  const own = { ...entry, versions: entry.versions.filter((v) => !v.readOnly) }
  stored = [...stored.filter((e) => !(e.siteId === entry.siteId && e.id === entry.id)), own]
  persist()
  return entry
}

function draftOf(entry: LibraryEntry, n: number): LibraryVersion {
  const version = entry.versions.find((v) => v.number === n)
  if (!version) throw new HttpError(404, 'version_not_found', 'SOP version not found.')
  if (version.readOnly) throw new HttpError(409, 'read_only', 'This version comes from the catalog and is read-only.')
  if (version.status !== 'draft') throw new HttpError(409, 'invalid_state', 'This version never changes. Create a new version.')
  return version
}

const text = (value: unknown, max: number, field: string): string => {
  const s = typeof value === 'string' ? value.trim() : ''
  if (!s || s.length > max) throw new HttpError(422, 'validation_error', `${field} must be 1 to ${max} characters.`)
  return s
}

const newVersion = (number: number, body: string, lang: Lang, changeNote: string, steps: Step[]): LibraryVersion => ({
  number,
  text: body,
  lang,
  createdAt: nowIso(),
  createdBy: 'device',
  changeNote,
  status: 'draft',
  steps,
  readOnly: false,
})

export function createSop(siteId: string, body: { title?: string; text?: string; changeNote?: string; taskId?: string; lang?: Lang }): LibraryEntry {
  const id = site(siteId)
  const lang = body.lang ?? publicCatalog.sites.find((s) => s.id === id)?.defaultSupervisorLanguage ?? 'en'
  const entry: LibraryEntry = {
    id: `sop_${Math.random().toString(36).slice(2, 12)}`,
    siteId: id,
    title: text(body.title, 200, 'title'),
    ...(body.taskId ? { taskId: body.taskId } : {}),
    seeded: false,
    versions: [newVersion(1, text(body.text, 8000, 'text'), lang, body.changeNote?.trim() ?? '', [])],
  }
  return save(entry)
}

export function addVersion(siteId: string, sopId: string, body: { text?: string; changeNote?: string; lang?: Lang }): LibraryEntry {
  const entry = entryOf(siteId, sopId)
  if (entry.seeded) throw new HttpError(403, 'forbidden', CATALOGUE_READ_ONLY)
  if (openDraft(entry)) throw new HttpError(409, 'draft_exists', 'This SOP already has a draft version.')
  const approved = entry.versions.filter((v) => v.status === 'approved')
  const base = approved[approved.length - 1] ?? entry.versions[entry.versions.length - 1]
  const number = (entry.versions[entry.versions.length - 1]?.number ?? 0) + 1
  const steps = structuredClone(approved[approved.length - 1]?.steps ?? [])
  entry.versions.push(newVersion(number, text(body.text, 8000, 'text'), body.lang ?? base?.lang ?? 'en', body.changeNote?.trim() ?? '', steps))
  return save(entry)
}

export function setSteps(siteId: string, sopId: string, n: number, steps: Step[]): LibraryEntry {
  const entry = entryOf(siteId, sopId)
  const version = draftOf(entry, n)
  const ids = new Set(steps.map((s) => s.id))
  if (steps.length < 1 || steps.length > 6 || ids.size !== steps.length || steps.some((s) => !s.text.trim())) {
    throw new HttpError(422, 'invalid_steps', 'Send 1 to 6 steps with unique ids and non-empty text.')
  }
  version.steps = structuredClone(steps)
  return save(entry)
}

export function approve(siteId: string, sopId: string, n: number): LibraryEntry {
  const entry = entryOf(siteId, sopId)
  const version = draftOf(entry, n)
  if (version.steps.length === 0) throw new HttpError(422, 'steps_required', 'Set the critical steps first.')
  Object.assign(version, { steps: withEssentials(version.steps), status: 'approved', approvedBy: 'device', approvedAt: nowIso() })
  return save(entry)
}

/**
 * At sign-off, a step with no "what the worker must state" gets its own text as its one essential (17 Oct, as the backend's
 * sop_library._with_essentials): the editor has no such field, and the judge needs one. Blank essentials count as none, since the
 * backend drops them when the steps are saved.
 */
const withEssentials = (steps: readonly Step[]): Step[] =>
  steps.map((s) => ((s.essential ?? []).some((e) => e.trim()) ? s : { ...s, essential: [s.text.trim()] }))

function approvedVersion(siteId: string, ref: SopRef): { entry: LibraryEntry; version: LibraryVersion } {
  const entry = listSops(siteId).find((e) => e.id === ref.sopId)
  const version = entry?.versions.find((v) => v.number === ref.version)
  if (!entry || !version) throw new HttpError(422, 'unknown_sop', 'sopRef names no version of this site’s library.')
  if (version.status !== 'approved') throw new HttpError(422, 'sop_not_approved', 'Only a signed-off version can start a briefing.')
  return { entry, version }
}

/** Endpoint 4 with `sopRef`: the version as the briefing's SOP, under the backend's rules. */
export function briefingSop(body: CreateBriefingBody & { sopRef: SopRef }): { id: string; version: string; title: string; text: string } {
  if (body.sop) throw new HttpError(422, 'sop_conflict', 'Send sop or sopRef, not both.')
  const { entry, version } = approvedVersion(body.siteId, body.sopRef)
  if (body.taskId !== (entry.taskId ?? 'custom')) throw new HttpError(422, 'sop_task_mismatch', 'sopRef is the SOP of another task.')
  if (version.lang !== body.supervisorLang) throw new HttpError(422, 'sop_language_mismatch', 'The steps are in another language.')
  return { id: entry.id, version: `v${version.number}`, title: entry.title, text: version.text }
}

/** Endpoint 8 on a library briefing: the approved steps, with no model call. */
export const approvedSteps = (siteId: string, ref: SopRef): Step[] => structuredClone(approvedVersion(siteId, ref).version.steps)

/** Every step field as the backend compares it, after validators.steps: text, hazard and essentials trimmed, empty essentials dropped. */
const compared = (steps: readonly Step[]): string =>
  JSON.stringify(
    steps.map((s) => [
      s.id,
      s.text.trim(),
      (s.hazard ?? '').trim(),
      (s.essential ?? []).map((e) => e.trim()).filter(Boolean),
      s.source ?? 'instruction',
      s.sopQuote?.trim() || null,
      s.speakable ?? true,
    ]),
  )

/** Endpoint 9 on a library briefing (security fixes A, H2): only the version's signed-off steps, unchanged and in order. */
export function requireSignedOffSteps(b: Pick<Briefing, 'siteId' | 'sop'> & { sopRef: SopRef }, steps: readonly Step[]): void {
  if (compared(steps) === compared(approvedSteps(b.siteId, b.sopRef))) return
  throw new HttpError(
    409,
    'sop_steps_locked',
    `These steps are signed off in ${b.sop.id} ${b.sop.version}. To change them, a safety officer signs off a new version, or start the briefing with Gemini's steps.`,
  )
}

/** The /sites/{siteId}/sops routes, or undefined for any other path. */
export function libraryRoute(method: string, path: string, body: Record<string, unknown>): LibraryEntry | { items: LibraryEntry[] } | undefined {
  const m = /^\/sites\/([^/]+)\/sops(?:\/([^/]+))?(?:\/versions(?:\/(\d+)\/(steps|approve))?)?$/.exec(path)
  if (!m) return undefined
  const [, siteId = '', sopId, n, action] = m
  const versions = path.includes('/versions')
  if (method === 'GET' && !sopId) return { items: listSops(siteId) }
  if (method === 'GET' && sopId && !versions) return entryOf(siteId, sopId)
  if (method === 'POST' && !sopId) return createSop(siteId, body)
  if (method === 'POST' && sopId && versions && !n) return addVersion(siteId, sopId, body)
  if (method === 'PUT' && sopId && action === 'steps') return setSteps(siteId, sopId, Number(n), (body.steps as Step[]) ?? [])
  if (method === 'POST' && sopId && action === 'approve') return approve(siteId, sopId, Number(n))
  throw new HttpError(405, 'method_not_allowed', 'Method not allowed.')
}
