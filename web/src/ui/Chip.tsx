import type { ButtonHTMLAttributes, ReactNode } from 'react'
import type { IconName } from '../theme/iconNames.ts'
import { cx } from './cx.ts'
import { Icon } from './Icon.tsx'

export type ChipTone = 'neutral' | 'primary' | 'success' | 'warning' | 'error' | 'strong-error'

const TONE: Record<ChipTone, string> = {
  neutral: 'bg-surface-container-high text-on-surface-variant',
  primary: 'bg-primary-container text-on-primary-container',
  success: 'bg-success-container text-on-success-container',
  warning: 'bg-warning-container text-on-warning-container',
  error: 'bg-error-container text-on-error-container',
  'strong-error': 'bg-error text-on-error',
}

interface StatusChipProps {
  tone?: ChipTone
  icon?: IconName
  children: ReactNode
  className?: string
  lang?: string
}

/** Non-interactive label. Always carries text (and usually an icon): colour is never the only signal. */
export function StatusChip({ tone = 'neutral', icon, children, className, lang }: StatusChipProps) {
  return (
    <span lang={lang} className={cx('inline-flex min-h-8 items-center gap-1.5 rounded-sm px-3 text-label-lg', TONE[tone], className)}>
      {icon && <Icon name={icon} filled className="text-[1.125rem]" />}
      {children}
    </span>
  )
}

interface AssistChipProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className' | 'children'> {
  icon?: IconName
  children: ReactNode
}

/** M3 assist chip: a small suggested action (48 px tall hit area). */
export function AssistChip({ icon, children, type = 'button', ...rest }: AssistChipProps) {
  return (
    <button
      type={type}
      className="state-layer inline-flex min-h-12 items-center gap-2 rounded-sm border border-outline px-4 text-label-lg text-on-surface"
      {...rest}
    >
      {icon && <Icon name={icon} className="text-[1.125rem] text-primary" />}
      {children}
    </button>
  )
}
