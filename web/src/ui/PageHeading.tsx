import { useEffect, useRef, type ReactNode } from 'react'
import { useLocation } from 'wouter'
import { cx } from './cx.ts'

interface PageHeadingProps {
  title: string
  /**
   * The screen's one context line, plain text above the title: "Crane lift · English → தமிழ் · Round 1 of 3". Not an eyebrow:
   * no capitals, no accent colour, no decoration (web/design.md).
   */
  context?: ReactNode
  subtitle?: ReactNode
  /** Plain-text title for document.title when `title` is not enough. */
  documentTitle?: string
  className?: string
}

// A fresh page load keeps the browser's normal focus start (first Tab = skip link). Only after the
// user has navigated inside the app does each new screen take focus, so a screen reader announces it.
const FIRST_PATH = typeof window === 'undefined' ? '' : window.location.pathname
let navigated = false

/**
 * Sets the document title; after in-app navigation also scrolls to the top and moves focus to the
 * returned heading ref, so a screen reader announces the new screen.
 */
export function usePageFocus(title: string) {
  const ref = useRef<HTMLHeadingElement>(null)
  const [path] = useLocation()
  useEffect(() => {
    document.title = `${title} · Say It Back`
  }, [title])
  // Route changes only: a changed title (UI language switch) must not pull focus off the control being used.
  useEffect(() => {
    if (path !== FIRST_PATH) navigated = true
    if (!navigated) return
    window.scrollTo({ top: 0 })
    ref.current?.focus({ preventScroll: true })
  }, [path])
  return ref
}

/** The screen's one h1, with at most one context line above it and one subtitle below. */
export function PageHeading({ title, context, subtitle, documentTitle, className }: PageHeadingProps) {
  const ref = usePageFocus(documentTitle ?? title)

  return (
    <header className={cx('space-y-2', className)}>
      {context && <div className="text-body-md text-on-surface-variant tabular-nums">{context}</div>}
      <h1 ref={ref} tabIndex={-1} className="text-headline-md text-on-surface sm:text-headline-lg">
        {title}
      </h1>
      {subtitle && <div className="max-w-2xl text-body-lg text-on-surface-variant">{subtitle}</div>}
    </header>
  )
}
