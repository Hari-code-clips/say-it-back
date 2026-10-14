// The running caption line per role.
//
// The relay's `caption.text` is cumulative for the current utterance (docs/API.md, Deviations):
// `final: false` carries the text so far and `final: true` the whole utterance. So every frame
// REPLACES the line; appending would repeat words. Worker captions arrive once, as a final frame.

export type CaptionRole = 'model' | 'worker'

export class CaptionMerger {
  private lines: Record<CaptionRole, string> = { model: '', worker: '' }

  /** Applies one caption frame and returns the line to display. A frame with no text keeps the line. */
  push(role: CaptionRole, text: string): string {
    if (text) this.lines[role] = text
    return this.lines[role]
  }

  /** Blank the line (new cue, new answer window). */
  reset(role: CaptionRole): void {
    this.lines[role] = ''
  }
}
