// Sentence splitting for the scripts: Latin, CJK, Devanagari/Odia danda and Myanmar full stop.

const SENTENCE = /[^.!?。！？।॥။]+[.!?。！？।॥။]*["'”’)\]]*\s*/gu

export function splitSentences(text: string): string[] {
  const parts = text.match(SENTENCE) ?? []
  return parts.map((s) => s.trim()).filter(Boolean)
}

/**
 * The sentences of a generated script. The backend writes one sentence per line and `stepMap` indexes
 * those lines (docs/API.md, Deviations), so a line break is authoritative. Text with none (a
 * single sentence, or hand-written text) falls back to punctuation.
 */
export function scriptSentences(text: string): string[] {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)
  return lines.length > 1 ? lines : splitSentences(text)
}

/** Where each sentence of `scriptSentences(text)` ends in `text`, so `text.slice(0, end)` keeps the script's own line breaks. */
export function sentenceEnds(text: string): number[] {
  let at = 0
  return scriptSentences(text).map((s) => {
    at = Math.max(at, text.indexOf(s, at)) + s.length
    return at
  })
}

/** One step of a segment's caption in Turn mode: show `text` (the segment from its start) once `frac` of a clip has played. */
export interface RevealStep {
  frac: number
  text: string
  /** The last step: `text` is the whole segment. */
  final: boolean
}

/**
 * When each sentence of `text` appears while TTS speaks it. A clip has no timing of its own, so a sentence appears after
 * as much of the clip as the characters before it are of the text: the first at once, the last before the clip ends, and
 * a one-sentence text just once, at 0. `chunkLengths` are the lengths of the TTS chunks in play order (chunkForTts), one
 * clip each; the steps come per chunk, `frac` being the share of that chunk's clip.
 */
export function revealPlan(text: string, chunkLengths: number[]): RevealStep[][] {
  const sentences = scriptSentences(text)
  const ends = sentenceEnds(text)
  const total = sentences.reduce((n, s) => n + s.length, 0)
  const spoken = chunkLengths.reduce((n, l) => n + l, 0)
  const plan: RevealStep[][] = chunkLengths.map(() => [])
  if (!plan.length || !total) return plan
  let before = 0
  let chunk = 0
  let from = 0 // characters of the text before this chunk
  sentences.forEach((s, i) => {
    const at = (before / total) * spoken
    while (chunk < plan.length - 1 && at >= from + chunkLengths[chunk]) from += chunkLengths[chunk++]
    const last = i === sentences.length - 1
    plan[chunk].push({ frac: (at - from) / (chunkLengths[chunk] || 1), text: last ? text : text.slice(0, ends[i]), final: last })
    before += s.length
  })
  return plan
}

/** Where each sentence of `text` begins and ends, trimmed. Characters no sentence matched (a run of "!" at the start) stay in between. */
function sentenceSpans(text: string): Array<{ from: number; to: number }> {
  const spans: Array<{ from: number; to: number }> = []
  for (const m of text.matchAll(SENTENCE)) {
    const from = (m.index ?? 0) + m[0].length - m[0].trimStart().length
    const to = (m.index ?? 0) + m[0].trimEnd().length
    if (to > from) spans.push({ from, to })
  }
  return spans
}

/**
 * Splits text into chunks of at most `max` characters on sentence boundaries (TTS takes 600). Every chunk is a slice of the
 * text itself, never sentences joined with a space of our own: the server speaks only what is part of the round's script
 * (docs/API.md, endpoint 12), and in Chinese, Japanese or Burmese there is no space between sentences to join them with.
 */
export function chunkForTts(text: string, max = 600): string[] {
  const clean = text.trim()
  if (!clean) return []
  if (clean.length <= max) return [clean]
  const chunks: string[] = []
  let start = 0 // the open chunk is clean.slice(start, end)
  let end = 0
  const close = () => {
    if (end > start) chunks.push(clean.slice(start, end))
  }
  for (const { from, to } of sentenceSpans(clean)) {
    if (to - start > max) {
      close() // the sentence does not fit after what is open: start the next chunk with it
      start = from
      while (to - start > max) {
        // a sentence longer than a chunk is cut on its last space (or mid-word when it has none)
        const space = clean.lastIndexOf(' ', start + max)
        const stop = space > start ? space : start + max
        chunks.push(clean.slice(start, stop))
        start = stop + clean.slice(stop).search(/\S/)
      }
    }
    end = to
  }
  close()
  return chunks
}
