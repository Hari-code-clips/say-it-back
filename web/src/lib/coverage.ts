import type { Script } from '../api/types.ts'
import { scriptSentences } from './sentences.ts'

// The delivery check (what Live said vs the approved script) is the server's: see delivery.ts. The browser applies no threshold.

export interface Coverage {
  /** Steps in scope that no instruction sentence delivers. */
  notDelivered: string[]
  /** Steps in scope that no question asks about. */
  notAsked: string[]
}

/** Mirrors the backend's code check, so the supervisor can see it holds before the worker hears anything. */
export function scriptCoverage(stepIds: readonly string[], script: Script): Coverage {
  const asked = new Set(script.questions.flatMap((q) => q.stepIds))
  return {
    notDelivered: stepIds.filter((id) => (script.stepMap[id]?.length ?? 0) === 0),
    notAsked: stepIds.filter((id) => !asked.has(id)),
  }
}

/** For each instruction sentence, the step ids it delivers (`stepMap` holds 0-based sentence indices). */
export function stepsBySentence(script: Script): { sentences: string[]; stepIds: string[][] } {
  const sentences = scriptSentences(script.instruction)
  const stepIds = sentences.map((_, i) => Object.keys(script.stepMap).filter((id) => script.stepMap[id]?.includes(i)))
  return { sentences, stepIds }
}
