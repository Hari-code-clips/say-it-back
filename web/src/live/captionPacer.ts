// Puts a model caption on the playback clock: a word is shown when the worker hears it, not when it arrives.
//
// Gemini Live sends a turn's audio about 4x faster than real time and the relay forwards the transcription between the
// audio frames, so a caption shown on arrival runs ahead of the voice by most of a long read-out (an 83 s read-out was
// fully captioned 20 s in). The Player queues the audio on the AudioContext clock; this schedules the text on the
// same clock. Turn mode uses it too: a TTS clip has no transcription, so its sentences are timed across the clip.

/** The AudioContext clock, and a timer. Apart from the Player so a test can drive both from one fake clock. */
export interface PacerClock {
  /** AudioContext time, in seconds. */
  now(): number
  /** Runs `fn` after `ms`; the returned function cancels it. */
  later(ms: number, fn: () => void): () => void
}

export const playerClock = (player: { readonly currentTime: number }): PacerClock => ({
  now: () => player.currentTime,
  later: (ms, fn) => {
    const timer = setTimeout(fn, ms)
    return () => clearTimeout(timer)
  },
})

/**
 * A frame's words are spread over at least this many seconds. The first frame of a turn arrives with a fraction of a
 * second of audio but holds about a second of words (0.15 s of audio, 15 characters, in the integration run).
 */
const MIN_SPAN_S = 0.5
/** A reveal this close to the clock counts as due, and a timer that wakes before the clock is due looks again after this long. */
const DUE_S = 0.005
const RECHECK_MS = 50

interface Reveal {
  at: number
  /** The whole caption from its start, not just the new words. */
  text: string
  final: boolean
}

const WORDS = typeof Intl.Segmenter === 'function' ? new Intl.Segmenter(undefined, { granularity: 'word' }) : null

/**
 * Where each word of `text` ends, the spaces and punctuation after it included, so the last end is `text.length`.
 * Words come from Intl.Segmenter, which also finds them in scripts written without spaces (Chinese, Burmese); without
 * it, a word is what sits between spaces. A hyphen keeps its two words together: Tamil takes English nouns with a
 * suffix ("breaker-ஐ"), and the caption should not stop at "breaker-".
 */
export function wordEnds(text: string): number[] {
  const ends: number[] = []
  if (WORDS) {
    const parts = [...WORDS.segment(text)]
    for (const [i, { segment, index, isWordLike }] of parts.entries()) {
      const end = index + segment.length
      if (isWordLike && ends.length && parts[i - 1]?.segment === '-' && parts[i - 2]?.isWordLike) ends[ends.length - 1] = end
      else if (isWordLike) ends.push(end)
      else if (ends.length) ends[ends.length - 1] = end
    }
  } else {
    for (const m of text.matchAll(/\S+\s*/g)) ends.push(m.index + m[0].length)
  }
  return ends.length ? ends : [text.length]
}

function commonPrefix(a: string, b: string): number {
  let i = 0
  while (i < a.length && i < b.length && a[i] === b[i]) i++
  return i
}

export class CaptionPacer {
  private readonly clock: PacerClock
  private readonly show: (text: string, final: boolean) => void
  private pending: Reveal[] = []
  private cancel: (() => void) | null = null
  /** The utterance in progress: the text of its latest frame, and where in the audio queue that frame arrived. */
  private text = ''
  private anchor: number | null = null

  constructor(clock: PacerClock, show: (text: string, final: boolean) => void) {
    this.clock = clock
    this.show = show
  }

  /**
   * Live: a model caption frame, `text` cumulative for the utterance, that arrived when the audio queued so far would
   * finish playing at `anchor` (the Player's `nextStart`).
   *
   * The transcription runs ahead of the audio it transcribes: in the integration run a turn's first frame arrived with
   * 0.15 s of audio and held about a second of words, and a turn's text was complete 0.8 to 3.6 s of audio before its
   * audio ended. So a frame belongs with the audio that follows it. Its first new word is shown when the audio queued before
   * it has played (`anchor`), and the rest follow across the next stretch of speech, taken to last as long as the audio
   * that arrived since the previous frame (about a second): a frame's words are spread over the second they are
   * spoken in, not all shown at its start. A final frame shows the whole utterance at `anchor`, the end of the audio.
   */
  frame(raw: string, final: boolean, anchor: number): void {
    const text = raw.trim()
    if (!text) return
    const from = commonPrefix(this.text, text)
    if (final) {
      this.cut(anchor, from)
      // A final frame with no partial before it holds the whole text and has no words to follow it by: show it now.
      this.pending.push({ at: this.anchor === null ? this.clock.now() : anchor, text, final })
      this.text = ''
      this.anchor = null
    } else {
      const start = from + Math.max(0, text.slice(from).search(/\S/)) // the first new word, past the space after the last one
      const ends = wordEnds(text).filter((end) => end > start)
      if (!ends.length) return
      const span = Math.max(MIN_SPAN_S, anchor - (this.anchor ?? anchor))
      this.cut(anchor, from)
      let before = start
      for (const end of ends) {
        this.pending.push({ at: anchor + (span * (before - start)) / (text.length - start), text: text.slice(0, end), final })
        before = end
      }
      this.text = text
      this.anchor = anchor
    }
    this.arm()
  }

  /** Show `text` when the clock reaches `at`; a time that has passed shows it now. Add reveals in time order. */
  add(at: number, text: string, final = false): void {
    this.pending.push({ at, text, final })
    this.arm()
  }

  /** The speech has finished playing: show the newest pending text now, so the whole utterance is on screen. */
  flush(): void {
    const last = this.pending.at(-1)
    this.drop()
    if (last) this.show(last.text, last.final)
  }

  /** The speech was flushed, interrupted or abandoned: what waited for it is never shown, and the next frame starts afresh. */
  drop(): void {
    this.cancel?.()
    this.cancel = null
    this.pending = []
    this.text = ''
    this.anchor = null
  }

  /**
   * Forget what a new frame replaces: reveals at or after `anchor` (its first word shows their text again), and
   * reveals past the first `keep` characters, which a revised transcription has changed.
   */
  private cut(anchor: number, keep: number): void {
    this.pending = this.pending.filter((r) => r.at < anchor && r.text.length <= keep)
  }

  private arm(recheckMs = 0): void {
    this.cancel?.()
    this.cancel = null
    const next = this.pending[0]
    if (next) this.cancel = this.clock.later(Math.max(recheckMs, (next.at - this.clock.now()) * 1000), () => this.fire())
  }

  private fire(): void {
    this.cancel = null
    const now = this.clock.now()
    let due: Reveal | undefined
    while (this.pending[0] && this.pending[0].at <= now + DUE_S) due = this.pending.shift()
    if (due) this.show(due.text, due.final)
    this.arm(due ? 0 : RECHECK_MS)
  }
}
