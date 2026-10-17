// Sending again on a weak signal (2026-10-16): exponential backoff with jitter, for a request whose server answer never arrived.
// Only an answer that did not come back is retried (offline, a dropped connection, a timeout): any reply the server gave, 4xx or
// 5xx, is final here, so a refusal is never repeated and a failed check is retried only by the supervisor. The check upload carries
// an Idempotency-Key (docs/API.md, Deviations 2026-10-16), so a retry of an upload that did reach the server is answered with the
// round it judged and is never judged or charged twice.
import { ApiError } from '../api/transport.ts'

export interface Backoff {
  /** The first wait, before jitter. */
  baseMs: number
  /** No wait is longer than this. */
  maxMs: number
}

/** About 1, 2, 4, 8, 16 s, then every 30 s or so, for as long as the screen waits. */
export const UPLOAD_BACKOFF: Backoff = { baseMs: 1_000, maxMs: 30_000 }

/**
 * The wait before retry number `attempt` (0-based): "equal jitter", half of the exponential step plus a random half, so phones
 * that lost the same mast do not all come back in the same second, and no wait is ever zero.
 */
export function backoffDelay(attempt: number, { baseMs, maxMs }: Backoff, random: () => number = Math.random): number {
  const step = Math.min(maxMs, baseMs * 2 ** Math.max(0, Math.min(attempt, 30)))
  return Math.round(step / 2 + (step / 2) * Math.min(1, Math.max(0, random())))
}

/** No answer came back from the server: the only failures that are sent again by themselves. */
export function unreachable(e: unknown): boolean {
  return e instanceof ApiError && e.status === 0 && (e.code === 'network' || e.code === 'timeout')
}

/** While a request waits to be sent again: since when (Date.now()), how many tries failed, and whether the phone says it is offline. */
export interface Waiting {
  since: number
  failures: number
  offline: boolean
}

export interface RetryDeps {
  now: () => number
  /** Resolves after `ms`, or as soon as the phone comes back online, whichever is first; rejects when `signal` aborts. */
  pause: (ms: number, signal?: AbortSignal) => Promise<void>
  online: () => boolean
  random?: () => number
}

export interface RetryOptions {
  /** Told each time a try fails and the next one waits, and with null once the request has an answer (or gives up). */
  onWait?: (waiting: Waiting | null) => void
  signal?: AbortSignal
  backoff?: Backoff
  deps?: RetryDeps
}

/** Run `send` until the server answers. Its answer, a success or an error reply, is returned or thrown as it came. */
export async function untilAnswered<T>(send: () => Promise<T>, { onWait, signal, backoff = UPLOAD_BACKOFF, deps = browserDeps() }: RetryOptions = {}): Promise<T> {
  let since: number | null = null
  for (let failures = 0; ; failures++) {
    try {
      const answer = await send()
      if (since !== null) onWait?.(null)
      return answer
    } catch (e) {
      if (!unreachable(e) || signal?.aborted) {
        if (since !== null) onWait?.(null)
        throw e
      }
      since ??= deps.now()
      onWait?.({ since, failures: failures + 1, offline: !deps.online() })
      await deps.pause(backoffDelay(failures, backoff, deps.random), signal)
    }
  }
}

/** The browser's clock, timers and online events. Outside a browser (tests, SSR) it only waits for the timer. */
export function browserDeps(): RetryDeps {
  const target = typeof window === 'undefined' ? undefined : window
  return {
    now: () => Date.now(),
    online: () => (typeof navigator === 'undefined' ? true : navigator.onLine !== false),
    pause: (ms, signal) =>
      new Promise<void>((resolve, reject) => {
        const done = () => {
          clearTimeout(timer)
          target?.removeEventListener('online', done)
          signal?.removeEventListener('abort', stop)
          resolve()
        }
        const stop = () => {
          clearTimeout(timer)
          target?.removeEventListener('online', done)
          reject(signal?.reason ?? new DOMException('Aborted', 'AbortError'))
        }
        const timer = setTimeout(done, ms)
        target?.addEventListener('online', done, { once: true })
        if (signal?.aborted) stop()
        else signal?.addEventListener('abort', stop, { once: true })
      }),
  }
}
