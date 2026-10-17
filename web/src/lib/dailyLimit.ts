import { ApiError } from '../api/transport.ts'

// Whether a call has answered 429 `daily_limit` since the page loaded: the day's Gemini calls are used up (docs/API.md,
// "Daily cap"). Each screen still shows that error where it happened; this lets the page also offer the recorded demo
// (src/shell/DailyLimitNotice.tsx), whichever screen hit the limit. Nothing is stored: a reload starts from false.

/** The day's Gemini calls are used up (429 `daily_limit`). Nothing succeeds before 00:00 UTC, so nothing offers a retry. */
export const isDailyLimit = (e: unknown): boolean => e instanceof ApiError && e.code === 'daily_limit'

/**
 * A failed call's Retry, for a snackbar: none for `daily_limit`, where the page shows DailyLimitNotice instead
 * (src/shell/DailyLimitNotice.tsx), because a retry cannot succeed until the budget resets.
 */
export function retryFor(e: unknown, label: string, retry: () => void): { actionLabel?: string; onAction?: () => void } {
  return isDailyLimit(e) ? {} : { actionLabel: label, onAction: retry }
}

export interface DailyLimitWatch {
  reached: () => boolean
  /** Hand it every failed call. Only `daily_limit` changes anything. */
  note: (e: unknown) => void
  /** For useSyncExternalStore. */
  subscribe: (listener: () => void) => () => void
}

export function createDailyLimitWatch(): DailyLimitWatch {
  let reached = false
  const listeners = new Set<() => void>()
  return {
    reached: () => reached,
    note(e) {
      if (reached || !isDailyLimit(e)) return
      reached = true
      for (const listener of listeners) listener()
    },
    subscribe(listener) {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
  }
}

/** This page's watch, fed by the API client (src/api/client.ts). */
export const dailyLimit = createDailyLimitWatch()
