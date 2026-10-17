/* Hallmark · component: press-and-hold button · genre: modern-minimal · theme: design.md
 * states: default (outlined, 48 px) · hover (state layer) · focus-visible (3 px ink ring) · active = holding (an ink bar fills along the bottom
 *         edge over 1.5 s; it keeps running under reduced motion because it is the countdown) · disabled · loading (`busy`)
 *         · error / success (`status`, same as Button) · confirmed (bar full until release)
 * input: pointer hold, or hold Space / Enter. A short press says `hint` (live). A click that arrives with no press (screen reader,
 *        switch control) opens `confirm` in a dialog instead, so the control never needs a gesture it cannot give.
 */
import { useEffect, useId, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react'
import type { IconName } from '../theme/iconNames.ts'
import { buttonClass, type ButtonStatus } from './buttonLook.ts'
import { Button } from './Button.tsx'
import { cx } from './cx.ts'
import { Dialog } from './Dialog.tsx'
import { Icon } from './Icon.tsx'
import { createHold, HOLD_MS, type Hold, type HoldPhase } from './holdToConfirm.ts'

interface HoldButtonProps {
  /** The label, e.g. "Hold to end the round". */
  children: ReactNode
  onConfirm: () => void
  /** Said when the press was too short, and the button's description: "Keep holding for 2 seconds." */
  hint: string
  /** What to ask when assistive technology activates the button without a hold. */
  confirm: { title: string; body?: string; confirmLabel: string; cancelLabel: string }
  icon?: IconName
  status?: ButtonStatus
  busy?: boolean
  disabled?: boolean
  /** Defaults to 1500 ms. */
  holdMs?: number
  className?: string
  lang?: string
}

const SHORT_HINT_MS = 2400

const realTimer = {
  later(ms: number, fn: () => void) {
    const id = setTimeout(fn, ms)
    return () => clearTimeout(id)
  },
}

export function HoldButton({ children, onConfirm, hint, confirm, icon, status, busy, disabled, holdMs = HOLD_MS, className, lang }: HoldButtonProps) {
  const hintId = useId()
  const [phase, setPhase] = useState<HoldPhase>('idle')
  const [short, setShort] = useState(false)
  const [asking, setAsking] = useState(false)
  const latest = useRef({ onConfirm, holdMs })
  latest.current = { onConfirm, holdMs }
  const shortTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const el = useRef<HTMLButtonElement>(null)
  // True from a pointer press until its click: that click is the end of a gesture we handled, not an assistive-technology activation.
  const gesture = useRef(false)
  const hold = useRef<Hold | null>(null)
  hold.current ??= createHold(
    realTimer,
    {
      onConfirm: () => latest.current.onConfirm(),
      onShortPress: () => {
        setShort(true)
        clearTimeout(shortTimer.current)
        shortTimer.current = setTimeout(() => setShort(false), SHORT_HINT_MS)
      },
      onPhase: setPhase,
    },
    holdMs,
  )

  useEffect(
    () => () => {
      hold.current?.abort()
      clearTimeout(shortTimer.current)
    },
    [],
  )

  const off = disabled || busy
  const holding = phase !== 'idle'

  const down = (e: PointerEvent<HTMLButtonElement>) => {
    if (off || (e.pointerType === 'mouse' && e.button !== 0)) return
    gesture.current = true
    setShort(false)
    try {
      e.currentTarget.setPointerCapture(e.pointerId)
    } catch {
      // A pointer that is already gone: the hold simply never starts.
    }
    hold.current?.press('pointer')
  }
  const up = () => {
    hold.current?.release('pointer')
    setTimeout(() => (gesture.current = false), 400) // normally the click clears it first
  }
  const move = (e: PointerEvent<HTMLButtonElement>) => {
    if (phase !== 'holding') return
    const r = e.currentTarget.getBoundingClientRect()
    const slack = 8
    if (e.clientX < r.left - slack || e.clientX > r.right + slack || e.clientY < r.top - slack || e.clientY > r.bottom + slack) hold.current?.abort()
  }
  const key = (e: KeyboardEvent<HTMLButtonElement>, isDown: boolean) => {
    if (e.key !== ' ' && e.key !== 'Enter') return
    e.preventDefault() // no synthetic click: the hold is the activation
    if (off) return
    if (isDown) {
      if (!e.repeat) {
        setShort(false)
        hold.current?.press('key')
      }
    } else {
      hold.current?.release('key')
    }
  }

  return (
    <div className={cx('flex flex-col items-start gap-2', className)}>
      <button
        ref={el}
        type="button"
        lang={lang}
        disabled={off}
        aria-busy={busy || undefined}
        aria-describedby={hintId}
        data-phase={phase}
        onPointerDown={down}
        onPointerUp={up}
        onPointerCancel={() => {
          gesture.current = false
          hold.current?.abort()
        }}
        onPointerMove={move}
        onKeyDown={(e) => key(e, true)}
        onKeyUp={(e) => key(e, false)}
        onBlur={() => hold.current?.abort()}
        onContextMenu={(e) => e.preventDefault()}
        onClick={() => {
          if (gesture.current) {
            gesture.current = false
            return
          }
          if (!off) setAsking(true)
        }}
        className={cx(buttonClass({ variant: 'outlined', size: 'md', status }, Boolean(icon) || Boolean(status) || Boolean(busy)), 'no-select relative overflow-hidden')}
      >
        {busy ? (
          <span aria-hidden="true" className="spinner size-5 animate-spin rounded-full border-2 border-current border-t-transparent" />
        ) : (
          (status || icon) && <Icon name={status ? (status === 'error' ? 'error' : 'check_circle') : (icon as IconName)} filled={Boolean(status)} className="text-[1.125rem]" />
        )}
        <span>{children}</span>
        {/* The countdown: an ink bar along the bottom edge, 8 px tall, full width when the hold is complete. */}
        <span
          aria-hidden="true"
          data-holding={holding}
          style={{ '--hold-ms': `${holdMs}ms` } as CSSProperties}
          className="hold-fill absolute inset-x-0 bottom-0 h-2 bg-primary"
        />
      </button>
      <span id={hintId} className="sr-only">
        {hint}
      </span>
      {/* Seen only after a press that was too short. A polite live region, always mounted, so the text is announced when it appears. */}
      <p role="status" aria-live="polite" className={cx('min-h-5 text-body-md text-on-surface-variant', !short && 'invisible')}>
        {short ? hint : ''}
      </p>
      <Dialog
        open={asking}
        onClose={() => setAsking(false)}
        title={confirm.title}
        actions={
          <>
            <Button variant="outlined" onClick={() => setAsking(false)}>
              {confirm.cancelLabel}
            </Button>
            <Button
              onClick={() => {
                setAsking(false)
                latest.current.onConfirm()
              }}
            >
              {confirm.confirmLabel}
            </Button>
          </>
        }
      >
        {confirm.body}
      </Dialog>
    </div>
  )
}
