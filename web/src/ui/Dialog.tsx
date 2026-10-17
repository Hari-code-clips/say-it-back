/* Hallmark · component: dialog · genre: modern-minimal · theme: design.md
 * Native <dialog>: focus trap, Esc, inert page and backdrop come from the browser. 16 px corners, a hairline and the one shadow that
 * floats. Opens with a 200 ms opacity + 6 px rise (index.css). Actions: full-width buttons stacked on a phone (the last, the
 * primary, at the bottom), one row from 600 px.
 */
import { useEffect, useId, useRef, type ReactNode } from 'react'

interface DialogProps {
  open: boolean
  onClose: () => void
  title: string
  children?: ReactNode
  /** Buttons, in reading order: the quieter ones first, the primary last. */
  actions: ReactNode
}

export function Dialog({ open, onClose, title, children, actions }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (open && !el.open) el.showModal()
    if (!open && el.open) el.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-xl border border-outline-variant bg-surface-container-lowest p-6 text-on-surface shadow-elev-3 backdrop:bg-scrim/40"
    >
      <h2 id={titleId} className="text-headline-sm">
        {title}
      </h2>
      {children && <div className="mt-3 text-body-lg text-on-surface-variant">{children}</div>}
      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-end">{actions}</div>
    </dialog>
  )
}
