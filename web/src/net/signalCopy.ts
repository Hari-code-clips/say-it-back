import { translate, type UiLang } from '../i18n/translate.ts'
import { clock } from '../lib/waitCopy.ts'
import type { Waiting } from './retry.ts'

/** The no-signal banner's two lines (src/shell/SignalBanner.tsx) for a wait that began at `since` (Date.now()), at `now`. */
export function signalCopy(waiting: Waiting, now: number, lang: UiLang): { title: string; body: string } {
  const waited = clock(Math.max(0, (now - waiting.since) / 1000))
  return {
    title: translate(lang, waiting.offline ? 'signal.noSignal' : 'signal.weak'),
    // Chinese sentences follow each other with no space.
    body: [translate(lang, 'signal.kept'), translate(lang, 'signal.waited', { time: waited })].join(lang === 'zh' ? '' : ' '),
  }
}
