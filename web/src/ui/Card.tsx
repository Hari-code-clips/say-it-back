import type { HTMLAttributes, ReactNode } from 'react'
import { cx } from './cx.ts'

type CardVariant = 'outlined' | 'filled' | 'elevated'

const VARIANT: Record<CardVariant, string> = {
  outlined: 'border border-outline-variant bg-surface-container-lowest',
  filled: 'bg-surface-container',
  elevated: 'bg-surface-container-low shadow-elev-1',
}

interface CardProps extends Omit<HTMLAttributes<HTMLElement>, 'className'> {
  variant?: CardVariant
  as?: 'div' | 'section' | 'article' | 'li'
  className?: string
  children: ReactNode
}

/** M3 card: 16 px corners, 16-24 px padding is up to the caller. */
export function Card({ variant = 'outlined', as: Tag = 'div', className, children, ...rest }: CardProps) {
  return (
    <Tag className={cx('rounded-lg', VARIANT[variant], className)} {...rest}>
      {children}
    </Tag>
  )
}

interface SectionProps {
  title: string
  hint?: string
  id?: string
  children: ReactNode
  className?: string
}

/** A titled group on a screen. The heading is an h2 under the screen's h1. */
export function Section({ title, hint, id, children, className }: SectionProps) {
  return (
    <section aria-labelledby={id} className={cx('space-y-3', className)}>
      <div className="space-y-1">
        <h2 id={id} className="text-title-lg text-on-surface">
          {title}
        </h2>
        {hint && <p className="text-body-md text-on-surface-variant">{hint}</p>}
      </div>
      {children}
    </section>
  )
}
