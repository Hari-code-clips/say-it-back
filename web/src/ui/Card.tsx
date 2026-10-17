/* Hallmark · component: card, rows, section · genre: modern-minimal · theme: design.md
 * One containment layer: a card is a hairline on paper, never a shadow, and never holds another card, a tinted box or a panel.
 * Inside it, rows are divided by hairlines (RowList). Not interactive, so no hover / active states of its own.
 */
import type { HTMLAttributes, ReactNode } from 'react'
import { cx } from './cx.ts'

type CardVariant = 'outlined' | 'filled' | 'elevated'

const VARIANT: Record<CardVariant, string> = {
  outlined: 'border border-outline-variant bg-surface-container-lowest',
  // A quiet panel on the page: a fill, no line. Use it alone, never inside an outlined card.
  filled: 'bg-surface-container-low',
  // Material's "elevated" is retired: depth is a hairline here, so it is the same as outlined.
  elevated: 'border border-outline-variant bg-surface-container-lowest',
}

interface CardProps extends Omit<HTMLAttributes<HTMLElement>, 'className'> {
  variant?: CardVariant
  as?: 'div' | 'section' | 'article' | 'li'
  className?: string
  children: ReactNode
}

/** 12 px corners; 16-24 px padding is up to the caller. */
export function Card({ variant = 'outlined', as: Tag = 'div', className, children, ...rest }: CardProps) {
  return (
    <Tag className={cx('rounded-lg', VARIANT[variant], className)} {...rest}>
      {children}
    </Tag>
  )
}

interface RowListProps {
  as?: 'ul' | 'ol' | 'div'
  className?: string
  children: ReactNode
}

/**
 * Hairline-divided rows, with no box around each row. Put it inside a Card (the card's own border closes it) or on the page
 * (a hairline above and below). Children are its rows, each with its own padding (px-4 py-3 is usual).
 */
export function RowList({ as: Tag = 'ul', className, children }: RowListProps) {
  return <Tag className={cx('divide-y divide-outline-variant', className)}>{children}</Tag>
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
