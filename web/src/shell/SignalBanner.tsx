/* Hallmark · component: the no-signal banner on the check's wait (supervisor, after the hand-back hold) · genre: modern-minimal ·
 * theme: design.md. A calm `info` banner (paper-2 fill, ink text, a mark), never red: nothing has failed, the answers are on the phone.
 * Supervisor language only: it shows on the supervisor's wait, never on a worker-held screen.
 * states: waiting (time waited ticks every second) · offline (the phone says it has no network) · gone (renders nothing).
 * Not interactive, so no hover, focus, active, disabled or loading states.
 */
import { useEffect, useState } from 'react'
import { useUiLang } from '../i18n/index.tsx'
import type { Waiting } from '../net/retry.ts'
import { signalCopy } from '../net/signalCopy.ts'
import { Banner } from '../ui/Feedback.tsx'

/** Shown while the check upload waits for a signal (useBriefingRun's `waiting`); nothing when it is not waiting. */
export function SignalBanner({ waiting }: { waiting: Waiting | null }) {
  const { lang } = useUiLang()
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!waiting) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [waiting])
  if (!waiting) return null
  const { title, body } = signalCopy(waiting, Math.max(now, waiting.since), lang)
  return (
    <Banner tone="info" icon="link_off" title={title} live="polite">
      <span className="tabular-nums">{body}</span>
    </Banner>
  )
}
