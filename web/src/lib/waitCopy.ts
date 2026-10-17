import { translate, type UiLang } from '../i18n/translate.ts'

// What a Gemini wait says while it lasts (build-notes/22, Task 7). A check can take 90 s when Gemini is busy, and a bar
// that only moves looks like a hang, so the wait shows a ticking counter and, from SLOW_AFTER_S on, a line saying that
// it is still working and how long it can take (the backend gives up at 120 s, SIB_REQUEST_TIMEOUT_S).

/** From this many seconds on, the wait says it is still working and can take up to 2 minutes. */
export const SLOW_AFTER_S = 45

/** A screen reader hears the counter at most this often (the visible one ticks every second). */
export const ANNOUNCE_EVERY_S = 15

/** "0:07", "1:30": minutes and seconds, whole seconds only. */
export function clock(elapsedS: number): string {
  const s = Math.max(0, Math.floor(elapsedS))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export interface WaitCopy {
  /** "0:12 elapsed", in the UI language. */
  counter: string
  /** The still-working line, or null before SLOW_AFTER_S. */
  slow: string | null
}

export function waitCopy(elapsedS: number, lang: UiLang): WaitCopy {
  return {
    counter: translate(lang, 'wait.elapsed', { time: clock(elapsedS) }),
    slow: elapsedS >= SLOW_AFTER_S ? translate(lang, 'wait.slow') : null,
  }
}

/** The elapsed time a screen reader is told: rounded down to ANNOUNCE_EVERY_S, and nothing before the first step. */
export function announcedElapsed(elapsedS: number): number | null {
  const step = Math.floor(Math.max(0, elapsedS) / ANNOUNCE_EVERY_S) * ANNOUNCE_EVERY_S
  return step > 0 ? step : null
}
