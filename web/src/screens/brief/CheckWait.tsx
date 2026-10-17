/* Hallmark · component: the check's wait (supervisor, after the hand-back hold) · genre: modern-minimal · theme: design.md
 * The three stages of the check as a STATIC numbered list, the time the check has really been running, and the stated bound. The API
 * reports no stage (docs/API.md endpoint 13 answers once, when it is done), so nothing here pretends to know which one is running: no
 * ticks, no per-stage spinner, no step that fills. The one moving thing is the indeterminate bar, which says only "working".
 * states: waiting (counter) · slow (from 45 s, a still-working line). Not interactive, so no hover, focus or active states.
 * motion: none beyond the indeterminate bar (reduced motion collapses it to a still bar, see index.css).
 */
import { useEffect, useState, type ReactNode } from 'react'
import { useT, useUiLang } from '../../i18n/index.tsx'
import { announcedElapsed, waitCopy } from '../../lib/waitCopy.ts'
import { LinearProgress } from '../../ui/Feedback.tsx'
import { Icon } from '../../ui/Icon.tsx'
import { Card, RowList } from '../../ui/Card.tsx'
import { secondsSince } from './handover.ts'

/** Whole seconds since `startedAt` (a clock reading, not a tick count, so a throttled background tab shows the true time). */
function useSecondsSince(startedAt: number): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  return secondsSince(startedAt, now)
}

const STAGES = ['brief.check.s1', 'brief.check.s2', 'brief.check.s3'] as const

/** The stated bound ("15–40 seconds") stays on one line: a break after the dash reads as two separate numbers. */
export function holdBoundTogether(text: string): ReactNode[] {
  return text.split(/(\d+–\d+\s?\S+)/u).map((part, i) =>
    i % 2 ? (
      <span key={i} className="whitespace-nowrap">
        {part}
      </span>
    ) : (
      part
    ),
  )
}

/** `startedAt`: when the check request went out (Date.now()), which is when the last answer was in. */
export function CheckWait({ startedAt }: { startedAt: number }) {
  const t = useT()
  const { lang } = useUiLang()
  const elapsed = useSecondsSince(startedAt)
  const { counter, slow } = waitCopy(elapsed, lang)
  const spoken = announcedElapsed(elapsed)
  return (
    // role="status" is atomic by default: aria-atomic="false" so a screen reader hears only the line that changed.
    <section role="status" aria-live="polite" aria-atomic="false" aria-labelledby="check-label" className="animate-fade-in space-y-4">
      <LinearProgress label={t('brief.checking')} />
      <p className="text-body-lg text-on-surface-variant">{holdBoundTogether(t('brief.checkingHint'))}</p>

      <div className="space-y-2">
        <p aria-hidden="true" className="text-label-lg tabular-nums text-on-surface">
          {counter}
        </p>
        <p className="sr-only">{spoken === null ? '' : waitCopy(spoken, lang).counter}</p>
        {slow && (
          <p className="flex items-start gap-2 text-body-md text-on-surface">
            <Icon name="hourglass_top" className="mt-0.5 text-[1.125rem]" />
            <span className="min-w-0">{slow}</span>
          </p>
        )}
      </div>

      <Card as="div" className="overflow-hidden">
        <h2 id="check-label" className="border-b border-outline-variant px-4 py-3 text-title-md text-on-surface">
          {t('brief.check.label')}
        </h2>
        <RowList as="ol">
          {STAGES.map((key, i) => (
            <li key={key} className="flex items-start gap-3 px-4 py-3">
              {/* A number, not a tick or a spinner: it says the order, never the progress. */}
              <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-full border-[1.5px] border-outline text-label-lg tabular-nums text-on-surface">
                {i + 1}
              </span>
              <span className="min-w-0 pt-1 text-body-lg text-on-surface">{t(key)}</span>
            </li>
          ))}
        </RowList>
      </Card>

      <p className="text-body-md text-on-surface-variant">{t('brief.check.note')}</p>
    </section>
  )
}
