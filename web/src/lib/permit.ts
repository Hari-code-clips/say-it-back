import type { BriefingSummary, Delivery, PermitLink } from '../api/types.ts'
import { translate, type UiLang } from '../i18n/translate.ts'

// Permit-to-work grouping (docs/API.md, "Permit-to-work grouping (v0.5.2)"): a briefing can belong to a high-risk permit,
// one worker per briefing, crews of 1 to 6. The slot number is the only per-worker field: never a name, ID or nationality
// (Rule 6). No React here, so it is unit-tested, and the mock backend validates with the same rules.

export const CREW_MAX = 6
const REF = /^[A-Za-z0-9._/-]{1,32}$/

/** The permit number as the contract takes it: 1-32 characters of letters, digits and . _ / -, after trimming. */
export const permitRefValid = (ref: string): boolean => REF.test(ref.trim())

/** A whole number from lo to hi. */
const inRange = (n: unknown, lo: number, hi: number): n is number => typeof n === 'number' && Number.isInteger(n) && n >= lo && n <= hi

/** The permit to send with a new briefing, trimmed; null when any part is outside the contract. */
export function permitLink(input: { ref: string; crewSize: number; slot: number }): PermitLink | null {
  const ref = input.ref.trim()
  if (!permitRefValid(ref) || !inRange(input.crewSize, 1, CREW_MAX) || !inRange(input.slot, 1, input.crewSize)) return null
  return { ref, crewSize: input.crewSize, slot: input.slot }
}

/** "PTW-123 · worker 2 of 3", in the UI language. */
export const permitLabel = (p: PermitLink, lang: UiLang): string => translate(lang, 'permit.chip', { ref: p.ref, slot: p.slot, crew: p.crewSize })

/** The same permit for the next worker on it, or null when this was the last slot. */
export const nextOnPermit = (p: PermitLink): PermitLink | null => (p.slot < p.crewSize ? { ...p, slot: p.slot + 1 } : null)

/** A crew size change keeps the slot inside the new crew. */
export const clampSlot = (slot: number, crewSize: number): number => Math.min(Math.max(1, slot), crewSize)

export interface PermitBoard {
  /** Slots whose latest decided briefing is a Go. */
  verified: number
  crewSize: number
  /** The stub's rule: released only when every slot 1..crewSize holds a Go. */
  status: 'released' | 'held'
}

/**
 * What the permit-to-work stub would show for `ref`, from this browser's own briefings: each slot's latest decision, and
 * released only when every slot has a Go. Mock mode shows it, labelled as mock; the real board lives in the permit system.
 */
export function permitBoard(items: readonly BriefingSummary[], ref: string, crewSize: number): PermitBoard {
  const key = ref.trim().toUpperCase()
  const latest = new Map<number, BriefingSummary>()
  for (const item of items) {
    const p = item.permit
    if (!p || p.ref.trim().toUpperCase() !== key || !item.decision) continue
    const seen = latest.get(p.slot)
    if (!seen?.decision || item.decision.at > seen.decision.at) latest.set(p.slot, item)
  }
  let verified = 0
  for (let slot = 1; slot <= crewSize; slot++) if (latest.get(slot)?.decision?.value === 'go') verified++
  return { verified, crewSize, status: verified === crewSize ? 'released' : 'held' }
}

/**
 * SIB_OUTBOX: the record's one line about the permit system, or null when no permit system is a target (Chat only, or the
 * outbox is off). Any permit target still retrying wins, then any that failed for good; else every one took it.
 */
export function permitDelivery(delivery: Delivery | null | undefined): 'delivered' | 'retrying' | 'notDelivered' | null {
  const permits = delivery?.targets.filter((t) => t.kind === 'permit') ?? []
  if (permits.length === 0) return null
  if (permits.some((t) => t.status === 'pending')) return 'retrying'
  return permits.some((t) => t.status === 'failed') ? 'notDelivered' : 'delivered'
}
