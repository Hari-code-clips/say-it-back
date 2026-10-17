/* Hallmark · component: a Gemini wait that is always on screen · genre: modern-minimal · theme: design.md
 * The 15-40 s waits (find the steps, write the script, write the re-explanation) used to sit below the controls, behind the sticky
 * bar at 320-414 px. This puts the panel at the top of the content, scrolls it into view the moment it appears (the supervisor may
 * have pressed the primary from deep in a long page), and leaves the polite live region of BusyPanel as it was.
 * states: appears (instant jump, no animation) · running (counter, still-working line from 45 s) · gone (the screen moves on or the
 * request failed and the controls return). Not interactive.
 */
import { useEffect, useRef } from 'react'
import { BusyPanel } from '../../ui/Feedback.tsx'

export function WaitInView({ title, hint }: { title: string; hint?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    // `nearest` leaves the page alone when the panel is already fully visible (the usual case on the short screens).
    ref.current?.scrollIntoView({ block: 'nearest' })
  }, [])
  return (
    <div ref={ref} className="scroll-mt-20">
      <BusyPanel title={title} hint={hint} />
    </div>
  )
}
