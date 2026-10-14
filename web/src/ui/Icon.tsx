import type { IconName } from '../theme/iconNames.ts'
import { cx } from './cx.ts'

interface IconProps {
  name: IconName
  /** Filled variant (selected / active states). */
  filled?: boolean
  className?: string
}

/** Material Symbols glyph. Decorative: pair it with visible text or give the control an aria-label. */
export function Icon({ name, filled, className }: IconProps) {
  return (
    <span aria-hidden="true" className={cx('icon', filled && 'icon-filled', className)}>
      {name}
    </span>
  )
}
