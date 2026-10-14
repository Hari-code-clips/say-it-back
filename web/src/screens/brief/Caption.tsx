import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { cx } from '../../ui/cx.ts'
import { nextFit, START } from './captionFit.ts'

interface CaptionProps {
  text: string
  /** Type classes from large to small. The caption steps down one at a time until its text fits, never past the last. */
  sizes: readonly string[]
  className?: string
}

/**
 * A live caption on the worker screen. The text can be as long as a 20-sentence read-out, the phone is not, so the box
 * is as tall as its text up to the room the layout leaves it (it shrinks as a flex item, see BriefStage), steps down
 * to a smaller type size when the text does not fit, and past that is anchored at the bottom: the newest words stay in
 * view and the oldest lines are cut off and fade out at the top (.caption-box in index.css).
 *
 * It is not a live region: the parent says aria-live="off", so a growing caption is never re-announced.
 */
export function Caption({ text, sizes, className }: CaptionProps) {
  const box = useRef<HTMLDivElement>(null)
  const [fit, setFit] = useState(START)

  // Measured before paint after every render (cheap), so the size a long caption settles on is the first one drawn.
  useLayoutEffect(() => {
    const el = box.current
    const content = el?.firstElementChild
    if (!el || !(content instanceof HTMLElement)) return
    const next = nextFit(fit, text !== '', content.offsetHeight > el.clientHeight + 1, sizes.length - 1)
    if (next !== fit) setFit(next)
  })

  // A resized window or a rotated phone gives the box a different height: start again from the large size.
  useEffect(() => {
    const restart = () => setFit(START)
    window.addEventListener('resize', restart)
    return () => window.removeEventListener('resize', restart)
  }, [])

  return (
    <div ref={box} data-clipped={fit.clipped} className={cx('caption-box script-text', sizes[fit.step], className)}>
      <p>{text}</p>
    </div>
  )
}
