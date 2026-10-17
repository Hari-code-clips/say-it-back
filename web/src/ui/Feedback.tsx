/* Hallmark · components: spinner, progress, banner, empty and error states · genre: modern-minimal · theme: design.md
 * Banner tones: info (neutral container), warning (neutral with a 1.5 px ink outline: amber is Ask again), error (red tint, the one
 * failure colour), success (green tint). Always a mark and a title or text. Not interactive, except the action a caller puts in.
 */
import type { ReactNode } from 'react'
import type { IconName } from '../theme/iconNames.ts'
import { Button } from './Button.tsx'
import { cx } from './cx.ts'
import { ElapsedHint } from './ElapsedHint.tsx'
import { Icon } from './Icon.tsx'

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cx('spinner inline-block size-6 animate-spin rounded-full border-[3px] border-primary border-t-transparent', className)}
    />
  )
}

/** Indeterminate linear progress. Pair it with a text status in an aria-live region. */
export function LinearProgress({ label }: { label: string }) {
  return (
    <div role="progressbar" aria-label={label} className="relative h-1 w-full overflow-hidden rounded-full bg-surface-container-highest">
      <span className="absolute inset-y-0 left-0 w-1/3 animate-indeterminate rounded-full bg-primary" />
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cx('skeleton', className)} />
}

interface BusyPanelProps {
  title: string
  hint?: string
}

/**
 * A slow Gemini-backed step: progress bar, a polite status line saying what is happening, and a counter of the time it has
 * taken so far (with a still-working line from 45 s), so a long wait never looks like a hang.
 */
export function BusyPanel({ title, hint }: BusyPanelProps) {
  return (
    // role="status" is atomic by default: without aria-atomic="false" a screen reader would read the whole panel again
    // each time the counter's spoken text changes (every 15 s). Now it reads only the changed line.
    <div role="status" aria-live="polite" aria-atomic="false" className="animate-fade-in space-y-3 rounded-lg bg-surface-container p-4 text-on-surface">
      <LinearProgress label={title} />
      <p className="text-title-md">{title}</p>
      {hint && <p className="text-body-md text-on-surface-variant">{hint}</p>}
      <ElapsedHint />
    </div>
  )
}

type Tone = 'info' | 'warning' | 'error' | 'success'

const TONE: Record<Tone, { box: string; icon: IconName }> = {
  info: { box: 'bg-surface-container text-on-surface', icon: 'info' },
  warning: { box: 'border-[1.5px] border-on-surface bg-surface text-on-surface', icon: 'warning' },
  error: { box: 'bg-error-container text-on-error-container', icon: 'error' },
  success: { box: 'bg-success-container text-on-success-container', icon: 'check_circle' },
}

interface BannerProps {
  tone?: Tone
  title?: string
  children?: ReactNode
  icon?: IconName
  /** Errors should announce themselves. */
  live?: 'polite' | 'assertive'
  action?: ReactNode
  className?: string
}

/** Inline message. Colour is never the only signal: every tone has its own mark and a title or text. */
export function Banner({ tone = 'info', title, children, icon, live, action, className }: BannerProps) {
  const look = TONE[tone]
  return (
    <div
      role={live === 'assertive' ? 'alert' : live ? 'status' : undefined}
      className={cx('flex gap-3 rounded-lg p-4', look.box, className)}
    >
      <Icon name={icon ?? look.icon} filled className="mt-0.5 text-[1.5rem]" />
      <div className="min-w-0 flex-1 space-y-1">
        {title && <p className="text-title-md">{title}</p>}
        {children && <div className="text-body-md">{children}</div>}
        {action && <div className="pt-2">{action}</div>}
      </div>
    </div>
  )
}

interface EmptyStateProps {
  icon: IconName
  title: string
  body?: string
  action?: ReactNode
}

/** Empty list: say what belongs here and offer the next step. */
export function EmptyState({ icon, title, body, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-outline-variant px-6 py-12 text-center">
      <span className="grid size-16 place-items-center rounded-full bg-surface-container-high text-on-surface">
        <Icon name={icon} className="text-[2rem]" />
      </span>
      <h2 className="text-title-lg">{title}</h2>
      {body && <p className="max-w-sm text-body-lg text-on-surface-variant">{body}</p>}
      {action && <div className="pt-2">{action}</div>}
    </div>
  )
}

interface ErrorStateProps {
  title: string
  message?: string
  retryLabel?: string
  onRetry?: () => void
}

/** Load failure: what failed, and the way out. */
export function ErrorState({ title, message, retryLabel, onRetry }: ErrorStateProps) {
  return (
    <div role="alert" className="flex flex-col items-center gap-3 rounded-lg bg-error-container px-6 py-10 text-center text-on-error-container">
      <Icon name="error" filled className="text-[2.5rem]" />
      <h2 className="text-title-lg">{title}</h2>
      {message && <p className="max-w-md text-body-lg">{message}</p>}
      {onRetry && retryLabel && (
        <Button variant="outlined" icon="refresh" onClick={onRetry} className="mt-2 border-on-error-container! text-on-error-container!">
          {retryLabel}
        </Button>
      )}
    </div>
  )
}
