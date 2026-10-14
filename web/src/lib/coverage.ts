import type { DeliveryCheck, Script } from '../api/types.ts'
import { scriptSentences } from './sentences.ts'

/** Live mode: below this a spoken segment is too far from the approved text to pass without a word to the supervisor. */
export const DELIVERY_MIN_SIMILARITY = 0.7

/** Segments the voice did not say, said in the wrong script, or said too differently from the approved script. */
export function deliveryIssues(delivery: readonly DeliveryCheck[]): DeliveryCheck[] {
  return delivery.filter((d) => !d.scriptOk || d.similarity < DELIVERY_MIN_SIMILARITY)
}

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
