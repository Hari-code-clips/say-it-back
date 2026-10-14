import { createContext, useContext } from 'react'
import type { Briefing } from '../api/types.ts'

export interface BriefingApi {
  briefing: Briefing
  /** Use a Briefing returned by a mutation. */
  setBriefing: (b: Briefing) => void
  /** Re-read the briefing from the server (after endpoints that return a Round). */
  refresh: () => Promise<Briefing>
}

export const BriefingContext = createContext<BriefingApi | null>(null)

export function useBriefing(): BriefingApi {
  const v = useContext(BriefingContext)
  if (!v) throw new Error('useBriefing needs a briefing route')
  return v
}
