/* Hallmark · component: Go / No-go choice · genre: modern-minimal · theme: design.md
 * A radio card like RadioCard, but 72 px instead of 96+: the decision's two choices must be fully above the sticky bar at 375 x 667 and up
 * with a reported problem open and with steps still open (audit item 1: the bar must not hide what it acts on, in any state). Native
 * radios (arrows, Tab, screen readers from the browser). Selected = 2 px ink border plus a check.
 * states: default · hover (state layer) · focus-visible (3 px ink ring, instant) · active (state layer) · selected · disabled (dashed:
 *         Go while a reported problem has no note; the hint says why) · loading / error / success belong to the screen's request.
 */
import { cx } from '../../ui/cx.ts'
import { Icon } from '../../ui/Icon.tsx'
import type { IconName } from '../../theme/iconNames.ts'

interface Props {
  name: string
  value: string
  checked: boolean
  onChange: () => void
  icon: IconName
  title: string
  hint: string
  /** Not selectable now; the hint says why. */
  disabled?: boolean
}

export function DecisionChoice({ name, value, checked, onChange, icon, title, hint, disabled }: Props) {
  return (
    <label className={cx('relative block', disabled && 'cursor-not-allowed')}>
      <input type="radio" name={name} value={value} checked={checked} onChange={onChange} disabled={disabled} className="peer sr-only" />
      <span
        className={cx(
          'state-layer flex h-full min-h-[4.5rem] items-center gap-3 rounded-lg border px-3 py-2.5 text-on-surface transition-colors',
          'border-outline-variant bg-surface-container-lowest',
          // 2 px ink border without shifting the layout: the 1 px border plus a 1 px ring drawn outside it.
          'peer-checked:border-primary peer-checked:ring-1 peer-checked:ring-primary',
          'peer-focus-visible:outline-[3px] peer-focus-visible:outline-offset-2 peer-focus-visible:outline-focus',
          'peer-disabled:border-dashed peer-disabled:border-outline peer-disabled:bg-surface-container-low peer-disabled:text-on-surface-variant',
        )}
      >
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-secondary-container text-on-secondary-container">
          <Icon name={icon} />
        </span>
        <span className="min-w-0 flex-1 break-words">
          <span className="block text-title-md text-on-surface">{title}</span>
          <span className="block text-body-md text-on-surface-variant">{hint}</span>
        </span>
        <Icon name="check_circle" filled className={cx('shrink-0 text-primary transition-opacity', checked ? 'opacity-100' : 'opacity-0')} />
      </span>
    </label>
  )
}
