import { useId, type InputHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { cx } from './cx.ts'
import { Icon } from './Icon.tsx'

interface FieldProps {
  label: string
  value: string
  onChange: (value: string) => void
  helper?: string
  error?: string
  maxLength?: number
  /** BCP-47 tag of the text being typed, so the right Noto font and shaping are used. */
  lang?: string
  className?: string
}

const CONTROL =
  'peer block w-full rounded-md border border-outline bg-transparent px-4 pb-2 pt-6 text-body-lg text-on-surface outline-none ' +
  'transition-colors placeholder:text-transparent hover:border-on-surface focus:border-primary focus:ring-1 focus:ring-primary ' +
  'aria-[invalid=true]:border-error aria-[invalid=true]:ring-error disabled:border-on-surface/12 disabled:text-on-surface/38'

const LABEL =
  'pointer-events-none absolute left-4 top-0 origin-left translate-y-4 text-body-lg text-on-surface-variant transition-transform ' +
  'peer-focus:translate-y-1.5 peer-focus:scale-[0.875] peer-focus:text-primary ' +
  'peer-[:not(:placeholder-shown)]:translate-y-1.5 peer-[:not(:placeholder-shown)]:scale-[0.875] ' +
  'peer-aria-[invalid=true]:text-error'

function Footer({ id, helper, error, count, max }: { id: string; helper?: string; error?: string; count: number; max?: number }) {
  if (!helper && !error && max === undefined) return null
  return (
    <div className="mt-1 flex justify-between gap-4 px-4 text-body-md">
      <p id={id} className={cx('flex items-start gap-1.5', error ? 'text-error' : 'text-on-surface-variant')}>
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

type InputProps = FieldProps & Omit<InputHTMLAttributes<HTMLInputElement>, keyof FieldProps | 'className' | 'type'>

export function TextField({ label, value, onChange, helper, error, maxLength, lang, className, ...rest }: InputProps) {
  const id = useId()
  const noteId = `${id}-note`
  return (
    <div className={className}>
      <div className="relative">
        <input
          id={id}
          type="text"
          value={value}
          lang={lang}
          placeholder=" "
          maxLength={maxLength}
          aria-invalid={error ? true : undefined}
          aria-describedby={error || helper || maxLength ? noteId : undefined}
          onChange={(e) => onChange(e.target.value)}
          className={cx(CONTROL, 'min-h-14')}
          {...rest}
        />
        <label htmlFor={id} className={LABEL}>
          {label}
        </label>
      </div>
      <Footer id={noteId} helper={helper} error={error} count={value.length} max={maxLength} />
    </div>
  )
}

type AreaProps = FieldProps & { rows?: number } & Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, keyof FieldProps | 'className' | 'rows'>

export function TextArea({ label, value, onChange, helper, error, maxLength, lang, rows = 3, className, ...rest }: AreaProps) {
  const id = useId()
  const noteId = `${id}-note`
  return (
    <div className={className}>
      <div className="relative">
        <textarea
          id={id}
          value={value}
          lang={lang}
          rows={rows}
          placeholder=" "
          aria-invalid={error ? true : undefined}
          aria-describedby={error || helper || maxLength ? noteId : undefined}
          onChange={(e) => onChange(e.target.value)}
          className={cx(CONTROL, 'script-text field-sizing-content resize-none')}
          {...rest}
        />
        <label htmlFor={id} className={LABEL}>
          {label}
        </label>
      </div>
      <Footer id={noteId} helper={helper} error={error} count={value.length} max={maxLength} />
    </div>
  )
}
