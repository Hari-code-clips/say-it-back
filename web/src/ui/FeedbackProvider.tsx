import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useLocation } from 'wouter'
import { Button } from './Button.tsx'
import { cx } from './cx.ts'
import { Icon } from './Icon.tsx'

// Snackbar (visual) and screen-reader announcements (status / alert live regions).
// The live regions are always mounted; only their text changes, which is what assistive tech needs.

export interface SnackOptions {
  message: string
  tone?: 'neutral' | 'error'
  actionLabel?: string
  onAction?: () => void
}

interface FeedbackApi {
  announce: (text: string, mode?: 'polite' | 'assertive') => void
  snack: (options: SnackOptions) => void
}

const FeedbackContext = createContext<FeedbackApi | null>(null)

export function useFeedback(): FeedbackApi {
  const api = useContext(FeedbackContext)
  if (!api) throw new Error('useFeedback needs <FeedbackProvider>')
  return api
}

const SNACK_MS = 6000

export function FeedbackProvider({ children, dismissLabel }: { children: ReactNode; dismissLabel: string }) {
  const [polite, setPolite] = useState('')
  const [assertive, setAssertive] = useState('')
  const [snack, setSnack] = useState<SnackOptions | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const announce = useCallback((text: string, mode: 'polite' | 'assertive' = 'polite') => {
    const set = mode === 'assertive' ? setAssertive : setPolite
    set('') // clear first so an identical message is announced again
    setTimeout(() => set(text), 50)
  }, [])

  const show = useCallback((options: SnackOptions) => {
    clearTimeout(timer.current)
    setSnack(options)
    timer.current = setTimeout(() => setSnack(null), options.tone === 'error' ? SNACK_MS * 2 : SNACK_MS)
  }, [])

  useEffect(() => () => clearTimeout(timer.current), [])

  // A snackbar belongs to the screen that raised it ("Step removed - Undo" means nothing elsewhere).
  const [location] = useLocation()
  useEffect(() => {
    clearTimeout(timer.current)
    setSnack(null)
  }, [location])

  const api = useMemo<FeedbackApi>(() => ({ announce, snack: show }), [announce, show])

  return (
    <FeedbackContext value={api}>
      {children}
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {polite}
      </div>
      <div className="sr-only" role="alert" aria-live="assertive" aria-atomic="true">
        {assertive}
      </div>
      <div
        role={snack?.tone === 'error' ? 'alert' : 'status'}
        aria-live={snack?.tone === 'error' ? 'assertive' : 'polite'}
        className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex justify-center px-4 pb-[calc(6.5rem+env(safe-area-inset-bottom))] sm:pb-8"
      >
        {snack && (
          <div
            className={cx(
              'pointer-events-auto flex min-h-12 max-w-xl animate-rise items-center gap-3 rounded-sm px-4 py-2 shadow-elev-3',
              snack.tone === 'error' ? 'bg-error text-on-error' : 'bg-inverse-surface text-inverse-on-surface',
            )}
          >
            {snack.tone === 'error' && <Icon name="error" filled />}
            <p className="flex-1 text-body-md">{snack.message}</p>
            {snack.actionLabel && (
              <Button
                variant="text"
                onClick={() => {
                  snack.onAction?.()
                  setSnack(null)
                }}
                className={snack.tone === 'error' ? 'text-on-error!' : 'text-inverse-primary!'}
              >
                {snack.actionLabel}
              </Button>
            )}
            <button
              type="button"
              aria-label={dismissLabel}
              onClick={() => setSnack(null)}
              className="state-layer grid size-12 shrink-0 place-items-center rounded-full"
            >
              <Icon name="close" />
            </button>
          </div>
        )}
      </div>
    </FeedbackContext>
  )
}
