/* Hallmark · component: chip · genre: modern-minimal · theme: design.md
 * StatusChip: non-interactive label, so no hover / active. Word + mark, never colour alone. 8 px radius, 32 px tall.
 * AssistChip: a small suggested action. default · hover (state layer) · focus-visible (ring) · active · disabled · loading (`busy`)
 *             · error / success (`status`).
 */
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import type { IconName } from '../theme/iconNames.ts'
import { CHIP_BASE, TONE, type ChipTone } from './chipLook.ts'
import { cx } from './cx.ts'
import { Icon } from './Icon.tsx'

export type { ChipTone } from './chipLook.ts'

interface StatusChipProps {
  tone?: ChipTone
  icon?: IconName
  children: ReactNode
  className?: string
  lang?: string
}

/** Non-interactive label. Always carries text (and usually a mark): colour is never the only signal. */
export function StatusChip({ tone = 'neutral', icon, children, className, lang }: StatusChipProps) {
  const look = TONE[tone]
  return (
    <span lang={lang} className={cx(CHIP_BASE, look.box, className)}>
      {icon && <Icon name={icon} filled={look.glyph === 'filled'} className="text-[1.125rem]" />}
      {children}
    </span>
  )
}

interface AssistChipProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className' | 'children'> {
  icon?: IconName
  busy?: boolean
  status?: 'error' | 'success'
  children: ReactNode
}

/** A small suggested action (48 px tall hit area). */
export function AssistChip({ icon, busy, status, disabled, children, type = 'button', ...rest }: AssistChipProps) {
  const lead = status ? (status === 'error' ? 'error' : 'check_circle') : icon
  return (
    <button
      type={type}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={cx(
        'state-layer inline-flex min-h-12 items-center gap-2 rounded-md border-[1.5px] px-4 text-label-lg active:translate-y-px',
        'disabled:pointer-events-none disabled:border-outline-variant disabled:text-outline',
        status === 'error' ? 'border-error text-error' : status === 'success' ? 'border-success text-success' : 'border-outline text-on-surface',
      )}
      {...rest}
    >
      {busy ? (
        <span aria-hidden="true" className="spinner size-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
      ) : (
        lead && <Icon name={lead} filled={Boolean(status)} className="text-[1.125rem]" />
      )}
      {children}
    </button>
  )
}
