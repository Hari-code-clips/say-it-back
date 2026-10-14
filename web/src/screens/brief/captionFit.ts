// How a live caption fits the room the layout gives it (see Caption.tsx).

export interface Fit {
  /** Index into the caption's type sizes; 0 is the large default. */
  step: number
  /** Even at the smallest size the text is longer than the box, so its oldest lines are cut off at the top. */
  clipped: boolean
}

export const START: Fit = { step: 0, clipped: false }

/**
 * The fit after measuring the caption. While the text overflows, step down one size at a time; at the smallest size
 * keep it and mark the caption clipped (the newest words stay in view: the box is anchored at the bottom). Sizes only
 * go down while a caption grows, so a long read-out never flickers between sizes; an empty caption (a new cue) starts
 * again from the large size. Returns `fit` itself when nothing changes.
 */
export function nextFit(fit: Fit, hasText: boolean, overflows: boolean, lastStep: number): Fit {
  if (!hasText) return fit.step === 0 && !fit.clipped ? fit : START
  if (overflows && fit.step < lastStep) return { step: fit.step + 1, clipped: false }
  return fit.clipped === overflows ? fit : { ...fit, clipped: overflows }
}
