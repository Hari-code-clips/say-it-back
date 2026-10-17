/* Hallmark · component: button · genre: modern-minimal · theme: design.md (ink fill, 12 px radius, never a pill)
 * states: default · hover (state layer, hover-capable pointers only) · focus-visible (3 px ink ring, instant) · active (state layer + 1 px press)
 *         · disabled (light neutral; `disabledReason` shows why and keeps it focusable) · loading (`busy`: spinner, label stays)
 *         · error (`status="error"`) · success (`status="success"`)
 * sizes: md 48 px · lg 64 px (the primary, full width at the bottom) · xl 76 px (the worker's one action)
 */
import { useId, type AnchorHTMLAttributes, type ButtonHTMLAttributes, type MouseEvent, type ReactNode } from 'react'
import { Link } from 'wouter'
import type { IconName } from '../theme/iconNames.ts'
import { availability, buttonClass, type ButtonStatus, type Look } from './buttonLook.ts'
import { cx } from './cx.ts'
import { Icon } from './Icon.tsx'

export type { ButtonSize, ButtonStatus, ButtonVariant } from './buttonLook.ts'

interface Content {
  icon?: IconName
  trailingIcon?: IconName
  busy?: boolean
  children?: ReactNode
}

type ButtonLook = Look & Content

const STATUS_ICON: Record<ButtonStatus, IconName> = { error: 'error', success: 'check_circle' }

function Inner({ icon, trailingIcon, busy, status, children, size = 'md' }: ButtonLook) {
  const iconSize = size === 'xl' ? 'text-[2.25rem]' : size === 'lg' ? 'text-[1.5rem]' : 'text-[1.125rem]'
  const lead = status ? STATUS_ICON[status] : icon
  return (
    <>
      {busy ? (
        <span aria-hidden="true" className={cx('spinner size-5 animate-spin rounded-full border-2 border-current border-t-transparent')} />
      ) : (
        lead && <Icon name={lead} filled={Boolean(status)} className={iconSize} />
      )}
      <span>{children}</span>
      {trailingIcon && !busy && <Icon name={trailingIcon} className={iconSize} />}
    </>
  )
}

interface ButtonOwnProps extends Look, Content {
  /** Visible text saying why the button is disabled. Shown next to it; the button stays focusable and announces it. */
  disabledReason?: string
}

type ButtonProps = ButtonOwnProps & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className' | 'children'>

export function Button({
  variant,
  size,
  icon,
  trailingIcon,
  busy,
  full,
  status,
  className,
  children,
  disabled,
  disabledReason,
  onClick,
  type = 'button',
  ...rest
}: ButtonProps) {
  const reasonId = useId()
  const { nativeDisabled, ariaDisabled, reason } = availability({ disabled, busy, disabledReason })
  const look = { variant, size, icon, trailingIcon, busy, full, status, className, children }
  const button = (
    <button
      type={type}
      disabled={nativeDisabled}
      aria-disabled={ariaDisabled || undefined}
      aria-busy={busy || undefined}
      aria-describedby={reason ? reasonId : undefined}
      // An explained-disabled button is still focusable, so its click must do nothing (and submit nothing).
      onClick={ariaDisabled ? (e: MouseEvent<HTMLButtonElement>) => e.preventDefault() : onClick}
      className={buttonClass(look, Boolean(icon) || Boolean(busy) || Boolean(status))}
      {...rest}
    >
      <Inner {...look} />
    </button>
  )
  if (!reason) return button
  return (
    <div className={cx('flex flex-col gap-2 sm:items-end', (full || size === 'xl') && 'w-full')}>
      <p id={reasonId} className="flex items-start gap-2 text-body-md text-on-surface-variant">
        <Icon name="info" className="mt-px text-[1.125rem]" />
        <span className="min-w-0">{reason}</span>
      </p>
      {button}
    </div>
  )
}

type LinkButtonProps = ButtonLook & { href: string } & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'className' | 'children' | 'href'>

/** A client-side route link that looks like a button. */
export function LinkButton({ variant, size, icon, trailingIcon, busy, full, status, className, children, href, ...rest }: LinkButtonProps) {
  const look = { variant, size, icon, trailingIcon, busy, full, status, className, children }
  return (
    <Link href={href} className={buttonClass(look, Boolean(icon) || Boolean(status))} {...rest}>
      <Inner {...look} />
    </Link>
  )
}

/** A plain download / external link that looks like a button. */
export function AnchorButton({ variant, size, icon, trailingIcon, busy, full, status, className, children, ...rest }: ButtonLook & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'className' | 'children'>) {
  const look = { variant, size, icon, trailingIcon, busy, full, status, className, children }
  return (
    <a className={buttonClass(look, Boolean(icon) || Boolean(status))} {...rest}>
      <Inner {...look} />
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
  standard: 'text-on-surface',
  tonal: 'bg-secondary-container text-on-secondary-container',
  filled: 'bg-primary text-on-primary',
}

/** 48 px square, 12 px corners. Disabled: the glyph goes light and stays readable (it has a label and a title). */
export function IconButton({ icon, label, tone = 'standard', className, type = 'button', ...rest }: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={cx(
        'state-layer inline-flex size-12 shrink-0 items-center justify-center rounded-md active:translate-y-px disabled:pointer-events-none disabled:text-outline',
        ICON_TONE[tone],
        className,
      )}
      {...rest}
    >
      <Icon name={icon} />
    </button>
  )
}
