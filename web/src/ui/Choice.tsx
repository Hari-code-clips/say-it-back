/* Hallmark · component: single-choice controls · genre: modern-minimal · theme: design.md
 * Native radio inputs (arrow keys, Tab and screen-reader semantics come from the browser); the radio is visually hidden and the sibling
 * <span> draws the control. Selected = ink (a fill or a 2 px ink border) plus a check: never a hue.
 * states: default · hover (state layer) · focus-visible (3 px ink ring, instant) · active (state layer) · disabled (dashed, with a reason)
 *         · selected. Error / success belong to the form that holds the group (a banner or a field message).
 */
import { useId, type ReactNode } from 'react'
import { cx } from './cx.ts'
import { Icon } from './Icon.tsx'

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

const FOCUS_INSET = 'peer-focus-visible:outline-[3px] peer-focus-visible:-outline-offset-[3px] peer-focus-visible:outline-focus'
const FOCUS_RING = 'peer-focus-visible:outline-[3px] peer-focus-visible:outline-offset-2 peer-focus-visible:outline-focus'

/** Segmented control (2-3 options, always one selected, with the selected check). */
export function SegmentedButton<T extends string>({ label, value, onChange, options, className }: GroupProps<T>) {
  const name = useId()
  return (
    <div role="radiogroup" aria-label={label} className={cx('flex overflow-hidden rounded-md border-[1.5px] border-outline', className)}>
      {options.map((o, i) => (
        <label key={o.value} className={cx('relative min-w-0 flex-1', i > 0 && 'border-l-[1.5px] border-outline')}>
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
              'state-layer flex min-h-12 items-center justify-center gap-2 px-3 text-label-lg text-on-surface transition-colors',
              'peer-checked:bg-primary peer-checked:text-on-primary peer-disabled:text-outline',
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

/** Choice chips used as a radio group (language pickers). */
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
              'state-layer flex min-h-12 items-center gap-2 rounded-md border-[1.5px] border-outline px-4 text-label-lg text-on-surface transition-colors',
              'peer-checked:border-primary peer-checked:bg-primary peer-checked:text-on-primary peer-disabled:border-outline-variant peer-disabled:text-outline',
              FOCUS_RING,
            )}
          >
            {value === o.value && <Icon name="check" className="text-[1.125rem]" />}
            <span lang={o.lang} className="text-body-lg">
              {o.label}
            </span>
            {o.sublabel && <span className="text-body-md">{o.sublabel}</span>}
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
  /** Not selectable now (e.g. Go while a reported problem is open). The subtitle should say why. */
  disabled?: boolean
  /** The id of a text that explains the card (a lock reason). */
  describedBy?: string
}

/** Selectable card (task picker, re-explain method, Go / No-go). Selected = 2 px ink border + a check; the card face does not change colour. */
export function RadioCard({ name, value, checked, onChange, icon, title, subtitle, lang, disabled, describedBy }: RadioCardProps) {
  return (
    <label className={cx('relative block', disabled && 'cursor-not-allowed')}>
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        onChange={onChange}
        disabled={disabled}
        aria-describedby={describedBy}
        className="peer sr-only"
      />
      <span
        className={cx(
          'state-layer flex h-full min-h-24 items-start gap-4 rounded-lg border p-4 text-on-surface transition-colors',
          'border-outline-variant bg-surface-container-lowest',
          // 2 px ink border without shifting the layout: the 1 px border plus a 1 px ring drawn outside it.
          'peer-checked:border-primary peer-checked:ring-1 peer-checked:ring-primary',
          FOCUS_RING,
          'peer-disabled:border-dashed peer-disabled:border-outline peer-disabled:bg-surface-container-low peer-disabled:text-on-surface-variant peer-disabled:before:opacity-0',
        )}
      >
        <span className="grid size-12 shrink-0 place-items-center rounded-full bg-secondary-container text-on-secondary-container">{icon}</span>
        <span className="min-w-0 flex-1 space-y-0.5 break-words">
          <span lang={lang} className="block text-title-md text-on-surface">
            {title}
          </span>
          {subtitle && <span className="block text-body-md text-on-surface-variant">{subtitle}</span>}
        </span>
        <Icon name="check_circle" filled className={cx('mt-0.5 text-primary transition-opacity', checked ? 'opacity-100' : 'opacity-0')} />
      </span>
    </label>
  )
}
