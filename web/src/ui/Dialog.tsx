import { useEffect, useId, useRef, type ReactNode } from 'react'

interface DialogProps {
  open: boolean
  onClose: () => void
  title: string
  children?: ReactNode
  /** Buttons, right-aligned. */
  actions: ReactNode
}

/** M3 basic dialog on the native <dialog>: focus trap, Esc to close and an inert page come from the browser. */
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
      className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-xl bg-surface-container-high p-6 text-on-surface shadow-elev-3 backdrop:bg-scrim/32"
    >
      <h2 id={titleId} className="text-headline-sm">
        {title}
      </h2>
      {children && <div className="mt-4 text-body-lg text-on-surface-variant">{children}</div>}
      <div className="mt-6 flex flex-wrap justify-end gap-2">{actions}</div>
    </dialog>
  )
}
