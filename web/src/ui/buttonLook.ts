// What a button looks like and when it is available, as plain data and functions (no JSX), so tests/ui can check the rules in
// web/design.md: 12 px radius (never a pill), 48 px minimum target, 64 px primary, and a disabled button that says why.
import { cx } from './cx.ts'

export type ButtonVariant = 'filled' | 'tonal' | 'outlined' | 'text' | 'error' | 'success'
export type ButtonSize = 'md' | 'lg' | 'xl'
/** The error and success states of a control: a coloured treatment plus a mark, never colour alone. */
export type ButtonStatus = 'error' | 'success'

export const BASE =
  'state-layer inline-flex select-none items-center justify-center gap-2 rounded-md text-center ' +
  'transition-[background-color,color,transform] active:translate-y-px ' +
  'disabled:pointer-events-none disabled:active:translate-y-0 aria-disabled:pointer-events-none aria-disabled:active:translate-y-0'

// A disabled filled button is a light neutral, so it can never be mistaken for a live ink one. It always comes with its reason.
const OFF_FILL =
  'disabled:bg-surface-container-high disabled:text-outline aria-disabled:bg-surface-container-high aria-disabled:text-outline'
const OFF_LINE =
  'disabled:border-outline-variant disabled:text-outline aria-disabled:border-outline-variant aria-disabled:text-outline'

export const VARIANT: Record<ButtonVariant, string> = {
  // Ink fill, paper text. The one primary per screen.
  filled: `bg-primary text-on-primary ${OFF_FILL}`,
  // Retired Material "tonal" fill: a secondary action is outlined now. Kept so existing screens compile and look right.
  tonal: `border-[1.5px] border-outline bg-transparent text-on-surface ${OFF_LINE}`,
  outlined: `border-[1.5px] border-outline bg-transparent text-on-surface ${OFF_LINE}`,
  text: 'bg-transparent text-on-surface underline decoration-outline decoration-1 underline-offset-4 disabled:text-outline aria-disabled:text-outline',
  // Hazard: the worker's problem button and discard. The only red button.
  error: `bg-error text-on-error ${OFF_FILL}`,
  success: `bg-success text-on-success ${OFF_FILL}`,
}

// Error / success replace the variant's colours. They are swapped in, never added next to the variant's own, because two
// utilities for the same property (bg-primary and bg-error) are won by stylesheet order, not by class order. The caller also
// swaps the leading mark (see Button.tsx), so the state is never colour alone.
const STATUS: Record<ButtonStatus, { solid: string; line: string }> = {
  error: { solid: `bg-error text-on-error ${OFF_FILL}`, line: `border-[1.5px] border-error bg-transparent text-error ${OFF_LINE}` },
  success: { solid: `bg-success text-on-success ${OFF_FILL}`, line: `border-[1.5px] border-success bg-transparent text-success ${OFF_LINE}` },
}

export const SIZE: Record<ButtonSize, string> = {
  // 48 px: every target is at least this tall.
  md: 'min-h-12 px-5 text-label-lg',
  // 64 px: the primary action, full width at the bottom of the screen.
  lg: 'min-h-16 px-6 text-title-md max-[22.5rem]:px-4',
  // 76 px: the worker's one action.
  xl: 'min-h-[4.75rem] w-full px-10 text-worker-sm font-semibold',
}

export interface Look {
  variant?: ButtonVariant
  size?: ButtonSize
  full?: boolean
  status?: ButtonStatus
  className?: string
}

export function buttonClass({ variant = 'filled', size = 'md', full, status, className }: Look, hasIcon: boolean): string {
  const solid = variant === 'filled' || variant === 'error' || variant === 'success'
  return cx(
    BASE,
    status ? (solid ? STATUS[status].solid : STATUS[status].line) : VARIANT[variant],
    SIZE[size],
    variant === 'text' && 'px-3',
    hasIcon && size === 'md' && variant !== 'text' && 'pl-4',
    full && 'w-full',
    className,
  )
}

export interface AvailabilityInput {
  disabled?: boolean
  busy?: boolean
  /** Visible text saying what is missing, e.g. "Choose Go or No-go first". */
  disabledReason?: string | null
}

export interface Availability {
  /** The `disabled` attribute. */
  nativeDisabled: boolean
  /** `aria-disabled="true"`: the button explains itself, so it stays in the tab order and keeps the reason under its description. */
  ariaDisabled: boolean
  /** The text to show next to the button, or undefined for none. */
  reason: string | undefined
}

/**
 * A disabled button with a reason must still be reachable: with `disabled` a keyboard or screen-reader user skips over it and
 * never hears why. So with a reason it becomes `aria-disabled` (focusable, click ignored) and the reason is also its description.
 * While busy the button is natively disabled and shows no reason: it is working, not blocked.
 */
export function availability({ disabled, busy, disabledReason }: AvailabilityInput): Availability {
  const reason = disabledReason?.trim() ? disabledReason : undefined
  const blocked = Boolean(disabled) && !busy
  const explained = blocked && reason !== undefined
  return {
    nativeDisabled: Boolean(busy) || (Boolean(disabled) && !explained),
    ariaDisabled: explained,
    reason: explained ? reason : undefined,
  }
}
