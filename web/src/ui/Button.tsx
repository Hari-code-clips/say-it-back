import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from 'wouter'
import type { IconName } from '../theme/iconNames.ts'
import { cx } from './cx.ts'
import { Icon } from './Icon.tsx'

export type ButtonVariant = 'filled' | 'tonal' | 'outlined' | 'text' | 'error' | 'success'
export type ButtonSize = 'md' | 'lg' | 'xl'

const BASE =
  'state-layer inline-flex select-none items-center justify-center gap-2 rounded-full text-center transition-[box-shadow,background-color,color] ' +
  'disabled:pointer-events-none aria-disabled:pointer-events-none'

const VARIANT: Record<ButtonVariant, string> = {
  filled: 'bg-primary text-on-primary hover:shadow-elev-1 disabled:bg-on-surface/12 disabled:text-on-surface/38',
  tonal:
    'bg-secondary-container text-on-secondary-container hover:shadow-elev-1 disabled:bg-on-surface/12 disabled:text-on-surface/38',
  outlined: 'border border-outline bg-transparent text-primary disabled:border-on-surface/12 disabled:text-on-surface/38',
  text: 'bg-transparent text-primary disabled:text-on-surface/38',
  error: 'bg-error-container text-on-error-container hover:shadow-elev-1 disabled:bg-on-surface/12 disabled:text-on-surface/38',
  success:
    'bg-success text-on-success hover:shadow-elev-1 disabled:bg-on-surface/12 disabled:text-on-surface/38',
}

const SIZE: Record<ButtonSize, string> = {
  md: 'min-h-12 px-6 text-label-lg',
  lg: 'min-h-14 px-8 text-title-md',
  xl: 'min-h-[4.75rem] w-full px-10 text-worker-sm font-semibold',
}

interface Look {
  variant?: ButtonVariant
  size?: ButtonSize
  icon?: IconName
  trailingIcon?: IconName
  busy?: boolean
  full?: boolean
  className?: string
  children?: ReactNode
}

export function buttonClass({ variant = 'filled', size = 'md', full, className }: Look, hasIcon: boolean): string {
  return cx(
    BASE,
    VARIANT[variant],
    SIZE[size],
    variant === 'text' && 'px-3',
    hasIcon && size === 'md' && variant !== 'text' && 'pl-4',
    full && 'w-full',
    className,
  )
}

function Content({ icon, trailingIcon, busy, children, size = 'md' }: Look) {
  const iconSize = size === 'xl' ? 'text-[2.25rem]' : size === 'lg' ? 'text-[1.5rem]' : 'text-[1.125rem]'
  return (
    <>
      {busy ? (
        <span aria-hidden="true" className={cx('spinner size-5 animate-spin rounded-full border-2 border-current border-t-transparent')} />
      ) : (
        icon && <Icon name={icon} className={iconSize} />
      )}
      <span>{children}</span>
      {trailingIcon && !busy && <Icon name={trailingIcon} className={iconSize} />}
    </>
  )
}

type ButtonProps = Look & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className' | 'children'>

export function Button({ variant, size, icon, trailingIcon, busy, full, className, children, disabled, type = 'button', ...rest }: ButtonProps) {
  const look = { variant, size, icon, trailingIcon, busy, full, className, children }
  return (
    <button
      type={type}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={buttonClass(look, Boolean(icon) || Boolean(busy))}
      {...rest}
    >
      <Content {...look} />
    </button>
  )
}

type LinkButtonProps = Look & { href: string } & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'className' | 'children' | 'href'>

/** A client-side route link that looks like a button. */
export function LinkButton({ variant, size, icon, trailingIcon, full, className, children, href, ...rest }: LinkButtonProps) {
  const look = { variant, size, icon, trailingIcon, full, className, children }
  return (
    <Link href={href} className={buttonClass(look, Boolean(icon))} {...rest}>
      <Content {...look} />
    </Link>
  )
}

/** A plain download / external link that looks like a button. */
export function AnchorButton({ variant, size, icon, trailingIcon, full, className, children, ...rest }: Look & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'className' | 'children'>) {
  const look = { variant, size, icon, trailingIcon, full, className, children }
  return (
    <a className={buttonClass(look, Boolean(icon))} {...rest}>
      <Content {...look} />
    </a>
  )
}

interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className' | 'children'> {
  icon: IconName
  /** Required: icon-only controls need an accessible name. */
  label: string
  tone?: 'standard' | 'tonal' | 'filled'
  className?: string
}

const ICON_TONE = {
  standard: 'text-on-surface-variant',
  tonal: 'bg-secondary-container text-on-secondary-container',
  filled: 'bg-primary text-on-primary',
}

export function IconButton({ icon, label, tone = 'standard', className, type = 'button', ...rest }: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={cx('state-layer inline-flex size-12 shrink-0 items-center justify-center rounded-full disabled:opacity-40', ICON_TONE[tone], className)}
      {...rest}
    >
      <Icon name={icon} />
    </button>
  )
}
