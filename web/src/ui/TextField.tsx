/* Hallmark · component: text field + text area · genre: modern-minimal · theme: design.md
 * Label above the field (never inside it). The border is 1.5 px in every state, so nothing shifts on focus.
 * states: default · hover (the border goes to ink) · focus-visible (3 px ink ring, instant) · active = typing (same as focus)
 *         · disabled · loading (`busy`: spinner at the right edge, the field stays editable) · error (red border + icon + message,
 *         `aria-invalid`) · success (`valid`: check at the right edge)
 */
import { useId, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from 'react'
import { cx } from './cx.ts'
import { Icon } from './Icon.tsx'

interface FieldProps {
  label: string
  value: string
  onChange: (value: string) => void
  helper?: string
  error?: string
  maxLength?: number
  /** Work in progress on the value (a check against the server): a spinner at the right edge; the field stays editable. */
  busy?: boolean
  /** The value was accepted: a check at the right edge. */
  valid?: boolean
  /** BCP-47 tag of the text being typed, so the right Noto font and shaping are used. */
  lang?: string
  className?: string
}

const CONTROL =
  'block w-full rounded-md border-[1.5px] border-outline bg-surface-container-lowest px-4 py-2.5 pr-12 text-body-lg text-on-surface ' +
  'transition-colors hover:border-on-surface placeholder:text-on-surface-variant ' +
  'aria-[invalid=true]:border-error aria-[invalid=true]:hover:border-error disabled:cursor-not-allowed disabled:border-outline-variant disabled:bg-surface-container-low disabled:text-outline'

function Mark({ busy, valid, error }: { busy?: boolean; valid?: boolean; error?: string }) {
  if (!busy && !valid && !error) return null
  return (
    <span className="pointer-events-none absolute right-4 top-3 grid size-6 place-items-center" aria-hidden="true">
      {busy ? (
        <span className="spinner size-5 animate-spin rounded-full border-2 border-on-surface-variant border-t-transparent" />
      ) : error ? (
        <Icon name="error" filled className="text-[1.5rem] text-error" />
      ) : (
        <Icon name="check_circle" filled className="text-[1.5rem] text-success" />
      )}
    </span>
  )
}

// The slot under a field keeps one line's height even when empty, so an error appearing never pushes the page down.
function Footer({ id, helper, error, count, max }: { id: string; helper?: string; error?: string; count: number; max?: number }) {
  return (
    <div className="mt-2 flex min-h-5 justify-between gap-4 text-body-md">
      <p id={id} className={cx('flex items-start gap-2', error ? 'text-error' : 'text-on-surface-variant')}>
        {error && <Icon name="error" filled className="mt-0.5 text-[1rem]" />}
        {error ?? helper}
      </p>
      {max !== undefined && (
        <span className={cx('shrink-0 tabular-nums', count > max ? 'text-error' : 'text-on-surface-variant')} aria-hidden="true">
          {count}/{max}
        </span>
      )}
    </div>
  )
}

function Frame({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-label-lg text-on-surface">
        {label}
      </label>
      <div className="relative">{children}</div>
    </div>
  )
}

type InputProps = FieldProps & Omit<InputHTMLAttributes<HTMLInputElement>, keyof FieldProps | 'className' | 'type'>

export function TextField({ label, value, onChange, helper, error, maxLength, busy, valid, lang, className, ...rest }: InputProps) {
  const id = useId()
  const noteId = `${id}-note`
  return (
    <div className={className}>
      <Frame id={id} label={label}>
        <input
          id={id}
          type="text"
          value={value}
          lang={lang}
          maxLength={maxLength}
          aria-invalid={error ? true : undefined}
          aria-busy={busy || undefined}
          aria-describedby={error || helper || maxLength ? noteId : undefined}
          onChange={(e) => onChange(e.target.value)}
          className={cx(CONTROL, 'min-h-12')}
          {...rest}
        />
        <Mark busy={busy} valid={valid} error={error} />
      </Frame>
      <Footer id={noteId} helper={helper} error={error} count={value.length} max={maxLength} />
    </div>
  )
}

type AreaProps = FieldProps & { rows?: number } & Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, keyof FieldProps | 'className' | 'rows'>

export function TextArea({ label, value, onChange, helper, error, maxLength, busy, valid, lang, rows = 3, className, ...rest }: AreaProps) {
  const id = useId()
  const noteId = `${id}-note`
  return (
    <div className={className}>
      <Frame id={id} label={label}>
        <textarea
          id={id}
          value={value}
          lang={lang}
          rows={rows}
          aria-invalid={error ? true : undefined}
          aria-busy={busy || undefined}
          aria-describedby={error || helper || maxLength ? noteId : undefined}
          onChange={(e) => onChange(e.target.value)}
          className={cx(CONTROL, 'script-text field-sizing-content resize-none')}
          {...rest}
        />
        <Mark busy={busy} valid={valid} error={error} />
      </Frame>
      <Footer id={noteId} helper={helper} error={error} count={value.length} max={maxLength} />
    </div>
  )
}
