import { useId, type ReactNode } from 'react'
import { cx } from './cx.ts'
import { Icon } from './Icon.tsx'

// Single-choice controls on native radio inputs: arrow keys, Tab and screen-reader semantics come
// from the browser. The radio is visually hidden; the sibling <span> draws the M3 control.

export interface Option<T extends string> {
  value: T
  label: ReactNode
  /** Secondary line (chips / cards). */
  sublabel?: string
  /** Language tag of the label text, e.g. "ta". */
  lang?: string
  disabled?: boolean
}

interface GroupProps<T extends string> {
  label: string
  value: T
  onChange: (value: T) => void
  options: readonly Option<T>[]
  className?: string
}

const FOCUS_INSET = 'peer-focus-visible:outline-[3px] peer-focus-visible:-outline-offset-[3px] peer-focus-visible:outline-primary'

/** M3 segmented button (2-3 options, always one selected, with the selected check). */
export function SegmentedButton<T extends string>({ label, value, onChange, options, className }: GroupProps<T>) {
  const name = useId()
  return (
    <div role="radiogroup" aria-label={label} className={cx('flex overflow-hidden rounded-full border border-outline', className)}>
      {options.map((o, i) => (
        <label key={o.value} className={cx('relative min-w-0 flex-1', i > 0 && 'border-l border-outline')}>
          <input
            type="radio"
            name={name}
            value={o.value}
            checked={value === o.value}
            disabled={o.disabled}
            onChange={() => onChange(o.value)}
            className="peer sr-only"
          />
          <span
            lang={o.lang}
            className={cx(
              'state-layer flex min-h-12 items-center justify-center gap-2 px-4 text-label-lg text-on-surface transition-colors',
              'peer-checked:bg-secondary-container peer-checked:text-on-secondary-container peer-disabled:opacity-40',
              FOCUS_INSET,
            )}
          >
            {value === o.value && <Icon name="check" className="text-[1.125rem]" />}
            <span className="truncate">{o.label}</span>
          </span>
        </label>
      ))}
    </div>
  )
}

/** M3 filter chips used as a radio group (language pickers). */
export function ChoiceChips<T extends string>({ label, value, onChange, options, className }: GroupProps<T>) {
  const name = useId()
  return (
    <div role="radiogroup" aria-label={label} className={cx('flex flex-wrap gap-2', className)}>
      {options.map((o) => (
        <label key={o.value} className="relative">
          <input
            type="radio"
            name={name}
            value={o.value}
            checked={value === o.value}
            disabled={o.disabled}
            onChange={() => onChange(o.value)}
            className="peer sr-only"
          />
          <span
            className={cx(
              'state-layer flex min-h-12 items-center gap-2 rounded-sm border border-outline px-4 text-label-lg text-on-surface transition-colors',
              'peer-checked:border-transparent peer-checked:bg-secondary-container peer-checked:text-on-secondary-container',
              'peer-focus-visible:outline-[3px] peer-focus-visible:outline-offset-2 peer-focus-visible:outline-primary',
            )}
          >
            {value === o.value && <Icon name="check" className="text-[1.125rem]" />}
            <span lang={o.lang} className="text-body-lg">
              {o.label}
            </span>
            {o.sublabel && <span className="text-body-md text-on-surface-variant peer-checked:text-on-secondary-container">{o.sublabel}</span>}
          </span>
        </label>
      ))}
    </div>
  )
}

interface RadioCardProps {
  name: string
  value: string
  checked: boolean
  onChange: () => void
  icon: ReactNode
  title: string
  subtitle?: string
  lang?: string
}

/** Selectable card (task picker, re-explain method). Selected = tonal fill + 2 px primary ring + check. */
export function RadioCard({ name, value, checked, onChange, icon, title, subtitle, lang }: RadioCardProps) {
  return (
    <label className="relative block">
      <input type="radio" name={name} value={value} checked={checked} onChange={onChange} className="peer sr-only" />
      <span
        className={cx(
          'state-layer flex h-full min-h-24 items-start gap-4 rounded-lg border p-4 text-on-surface transition-colors',
          'border-outline-variant bg-surface-container-lowest',
          'peer-checked:border-primary peer-checked:bg-primary-container/45 peer-checked:ring-2 peer-checked:ring-primary',
          'peer-focus-visible:outline-[3px] peer-focus-visible:outline-offset-2 peer-focus-visible:outline-primary',
        )}
      >
        <span className="grid size-12 shrink-0 place-items-center rounded-full bg-secondary-container text-on-secondary-container">{icon}</span>
        <span className="min-w-0 flex-1 space-y-0.5">
          <span lang={lang} className="block text-title-md text-on-surface">
            {title}
          </span>
          {subtitle && <span className="block text-body-md text-on-surface-variant">{subtitle}</span>}
        </span>
        <Icon
          name="check_circle"
          filled
          className={cx('mt-0.5 text-primary transition-opacity', checked ? 'opacity-100' : 'opacity-0')}
        />
      </span>
    </label>
  )
}
