import type { PacerClock } from '../../src/live/captionPacer.ts'

/**
 * One fake timeline for the AudioContext clock and for timers, so a test moves both together. `advanceTo` runs the
 * timers that fall due on the way, in order, each with `now()` at its own due time.
 */
export class FakeClock implements PacerClock {
  time = 0
  private timers: Array<{ at: number; seq: number; fn: () => void }> = []
  private seq = 0

  now = (): number => this.time

  later = (ms: number, fn: () => void): (() => void) => {
    const timer = { at: this.time + ms / 1000, seq: this.seq++, fn }
    this.timers.push(timer)
    return () => {
      this.timers = this.timers.filter((t) => t !== timer)
    }
  }

  advanceTo(time: number): void {
    for (;;) {
      const next = this.timers.filter((t) => t.at <= time).sort((a, b) => a.at - b.at || a.seq - b.seq)[0]
      if (!next) break
      this.timers = this.timers.filter((t) => t !== next)
      this.time = Math.max(this.time, next.at)
      next.fn()
    }
    this.time = Math.max(this.time, time)
  }

  /** Timers still waiting: a dropped caption must leave none. */
  get waiting(): number {
    return this.timers.length
  }
}
