// The press-and-hold gesture as a small state machine with an injected timer, so tests/ui can drive it with a fake clock.
// ui/HoldButton.tsx wires it to pointer and keyboard events. Used for the supervisor's exit on a worker screen: a worker
// who taps the corner by accident, or a child who holds the phone, cannot end the round (a tap or a short press only says "keep holding").

/** How long the press must last, in ms. Long enough that no accident reaches it, short enough for a gloved thumb. */
export const HOLD_MS = 1500

/** Anything with a `later` that returns its own cancel (tests/helpers/fakeClock.ts has one). */
export interface HoldTimer {
  later(ms: number, fn: () => void): () => void
}

/** What is holding: one source at a time, so a pointer and a key (or two fingers) cannot add up. */
export type HoldSource = 'pointer' | 'key'
export type HoldPhase = 'idle' | 'holding' | 'confirmed'

export interface HoldEvents {
  /** Called once per completed hold, at `durationMs`. */
  onConfirm(): void
  /** Released before the time was up. */
  onShortPress?(): void
  onPhase?(phase: HoldPhase): void
}

export interface Hold {
  readonly phase: HoldPhase
  /** Start holding. Ignored unless idle (key auto-repeat, a second finger, a hold that already confirmed). */
  press(source: HoldSource): void
  /** The pressing input ended normally (pointer up, key up). Ignored from any other source. */
  release(source: HoldSource): void
  /** The press was interrupted: pointer left the button, focus moved, the touch was cancelled, the page was hidden. Silent. */
  abort(): void
}

export function createHold(timer: HoldTimer, events: HoldEvents, durationMs: number = HOLD_MS): Hold {
  let phase: HoldPhase = 'idle'
  let source: HoldSource | null = null
  let cancel: (() => void) | null = null

  const setPhase = (next: HoldPhase) => {
    phase = next
    events.onPhase?.(next)
  }
  const stopTimer = () => {
    cancel?.()
    cancel = null
  }

  return {
    get phase() {
      return phase
    },
    press(by) {
      if (phase !== 'idle') return
      source = by
      setPhase('holding')
      cancel = timer.later(durationMs, () => {
        cancel = null
        setPhase('confirmed')
        events.onConfirm()
      })
    },
    release(by) {
      if (by !== source) return
      source = null
      if (phase === 'holding') {
        stopTimer()
        setPhase('idle')
        events.onShortPress?.()
      } else if (phase === 'confirmed') {
        setPhase('idle')
      }
    },
    abort() {
      source = null
      if (phase === 'idle') return
      stopTimer()
      setPhase('idle')
    },
  }
}
