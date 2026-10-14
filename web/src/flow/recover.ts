import { ApiError } from '../api/client.ts'
import type { Briefing } from '../api/types.ts'
import { defaultPhase } from './phases.ts'

/**
 * A 409 `invalid_state` usually means the server is ahead of this screen: a request succeeded but its
 * response was lost (a dropped connection or a client timeout), or the briefing was changed elsewhere. Re-read the
 * briefing and go to the screen its state allows, instead of retrying into the same 409 forever.
 * Returns true when it handled the error.
 */
export async function recoverFromConflict(e: unknown, refresh: () => Promise<Briefing>, go: (path: string) => void): Promise<boolean> {
  if (!(e instanceof ApiError) || e.code !== 'invalid_state') return false
  try {
    const fresh = await refresh()
    go(`/b/${fresh.id}/${defaultPhase(fresh)}`)
    return true
  } catch {
    return false
  }
}
