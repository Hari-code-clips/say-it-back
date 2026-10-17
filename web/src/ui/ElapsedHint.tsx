/* Hallmark · component: Gemini wait counter · genre: modern-minimal · theme: design.md
 * states: default (counter) · slow (from 45 s, a still-working line). Not interactive, so no hover, focus or active states.
 * motion: none. The counter is text that changes once a second; nothing slides or fades, so reduced motion has nothing to cut.
 */
import { useUiLang } from '../i18n/index.tsx'
import { announcedElapsed, waitCopy } from '../lib/waitCopy.ts'
import { useElapsedSeconds } from '../lib/useElapsed.ts'
import { cx } from './cx.ts'
import { Icon } from './Icon.tsx'

/**
 * The ticking part of a Gemini wait: "0:12 elapsed", and from 45 s a line saying it is still working (src/lib/waitCopy.ts).
 * Place it inside a polite live region (BusyPanel is one). The visible counter is hidden from screen readers, which hear
 * the time every 15 s instead of every second; the still-working line is announced once, when it appears.
 */
export function ElapsedHint({ className }: { className?: string }) {
  const { lang } = useUiLang()
  const elapsed = useElapsedSeconds()
  const { counter, slow } = waitCopy(elapsed, lang)
  const spoken = announcedElapsed(elapsed)
  return (
    <div className={cx('space-y-2', className)}>
      <p aria-hidden="true" className="text-label-lg tabular-nums">
        {counter}
      </p>
      <p className="sr-only">{spoken === null ? '' : waitCopy(spoken, lang).counter}</p>
      {slow && (
        <p className="flex items-start gap-2 text-body-md">
          <Icon name="hourglass_top" className="mt-0.5 text-[1.125rem]" />
          <span className="min-w-0">{slow}</span>
        </p>
      )}
    </div>
  )
}
