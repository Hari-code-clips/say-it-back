import { wavBytes } from '../audio/wav.ts'
import { longScriptOn } from './longScripts.ts'

// Synthetic "speech": syllable-shaped bursts of a harmonic voice, so the player, the orb and the
// level meters have something to move with. It is not speech and is never mistaken for it:
// mock mode is labelled everywhere.

/** Deterministic pseudo-random generator, so the same text always sounds the same. */
function rng(seed: number) {
  let s = seed * 9301 + 49297
  return () => {
    s = (s * 9301 + 49297) % 233280
    return s / 233280
  }
}

export function speechPcm(seconds: number, rate: number, seed = 1): Int16Array {
  const n = Math.max(1, Math.floor(seconds * rate))
  const out = new Int16Array(n)
  const rand = rng(seed)
  let phase = 0
  let t = 0.05
  while (t < seconds - 0.15) {
    const len = 0.12 + rand() * 0.14
    const f0 = 105 + rand() * 55
    const i0 = Math.floor(t * rate)
    const i1 = Math.min(n, Math.floor((t + len) * rate))
    for (let i = i0; i < i1; i++) {
      const u = (i - i0) / Math.max(1, i1 - i0)
      const env = Math.sin(Math.PI * u) ** 1.5
      const f = f0 * (1 + 0.08 * Math.sin(2 * Math.PI * 5 * (i / rate)) + 0.1 * (u - 0.5))
      phase += (2 * Math.PI * f) / rate
      let v = 0
      for (let h = 1; h <= 8; h++) v += Math.sin(h * phase) / h ** 1.3
      out[i] = Math.round((v * env * 0.22 * 32767) / 2.2)
    }
    t += len + (rand() < 0.2 ? 0.18 + rand() * 0.2 : 0.02 + rand() * 0.05)
  }
  return out
}

export function speechWav(seconds: number, rate: number, seed = 1): Blob {
  return new Blob([wavBytes(speechPcm(seconds, rate, seed), rate)], { type: 'audio/wav' })
}

/**
 * Seconds of mock speech for a line of text: about 15 characters a second, clamped to 1.4-6 s. With the long-script QA
 * flag (./longScripts.ts) there is no upper clamp, and Chinese runs at 5 characters a second, so a 6- or 21-sentence
 * read-out lasts about as long as the real model's (25 s and 83 s) and a caption can be compared with the speech.
 */
export const spokenSeconds = (text: string): number =>
  longScriptOn() ? Math.max(1.4, text.length / (/[\u3400-\u9fff]/.test(text) ? 5 : 15)) : Math.min(6, Math.max(1.4, text.length / 15))

/** A stable small number from a string, for seeding. */
export function seedOf(text: string): number {
  let h = 7
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) % 100003
  return h + 1
}
