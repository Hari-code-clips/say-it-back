// The worker's answer clips, in memory only: playable on the Result screen, never written to
// storage (the contract keeps audio out of the record unless SIB_KEEP_AUDIO is set server-side).
// 2026-10-16: the one exception is a check upload still owed on a weak signal, kept in IndexedDB until
// its check has an answer (src/net/queue.ts); the decision deletes that too.
import { uploads } from '../net/queue.ts'

const store = new Map<string, Record<string, Blob>>()

export const clipKey = (briefingId: string, round: number): string => `${briefingId}:${round}`

export const saveClips = (key: string, clips: Record<string, Blob>): void => {
  store.set(key, clips)
}

export const getClips = (key: string): Record<string, Blob> | undefined => store.get(key)

/** Forget every clip of a briefing (called once the decision is recorded). */
export function dropClips(briefingId: string): void {
  for (const key of [...store.keys()]) if (key.startsWith(`${briefingId}:`)) store.delete(key)
  void uploads.dropBriefing(briefingId) // 2026-10-16: and any upload still owed on this phone (src/net/queue.ts)
}

/** Forget a briefing's clips when it is decided: a decision recorded elsewhere, or whose response was lost, counts too. */
export function dropClipsIfDecided(briefing: { id: string; status: string }): void {
  if (briefing.status === 'decided') dropClips(briefing.id)
}
