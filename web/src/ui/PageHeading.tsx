import { useEffect, useRef, type ReactNode } from 'react'
import { useLocation } from 'wouter'
import { cx } from './cx.ts'

interface PageHeadingProps {
  title: string
  /** Small line above the title (e.g. "Step 2 of 7"). */
  eyebrow?: string
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

/** The screen's one h1. */
export function PageHeading({ title, eyebrow, subtitle, documentTitle, className }: PageHeadingProps) {
  const ref = usePageFocus(documentTitle ?? title)

  return (
    <header className={cx('space-y-2', className)}>
      {eyebrow && <p className="text-label-lg uppercase tracking-wide text-primary">{eyebrow}</p>}
      <h1 ref={ref} tabIndex={-1} className="text-headline-md font-semibold text-on-surface sm:text-headline-lg">
        {title}
      </h1>
      {subtitle && <div className="max-w-2xl text-body-lg text-on-surface-variant">{subtitle}</div>}
    </header>
  )
}
