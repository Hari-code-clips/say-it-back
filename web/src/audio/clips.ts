// The worker's answer clips, in memory only: playable on the Result screen, never written to
// storage (the contract keeps audio out of the record unless SIB_KEEP_AUDIO is set server-side).

const store = new Map<string, Record<string, Blob>>()

export const clipKey = (briefingId: string, round: number): string => `${briefingId}:${round}`

export const saveClips = (key: string, clips: Record<string, Blob>): void => {
  store.set(key, clips)
}

export const getClips = (key: string): Record<string, Blob> | undefined => store.get(key)

/** Forget every clip of a briefing (called once the decision is recorded). */
export function dropClips(briefingId: string): void {
  for (const key of [...store.keys()]) if (key.startsWith(`${briefingId}:`)) store.delete(key)
}
