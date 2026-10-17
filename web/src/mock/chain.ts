// The record chain of docs/API.md ("Record chain"), played by the mock: every state change appends one event in the same update,
// `hash = sha256_hex(prevHash + "\n" + canonical(event without hash and prevHash))`, and content is bound by digest. Verify
// (endpoint 25) recomputes the links and the digests from the record as stored now. Synchronous, so the mock store stays simple.
import type { Briefing, ChainEvent, ChainEventType, VerifyResult } from '../api/types.ts'

const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
])

const rotr = (x: number, n: number) => (x >>> n) | (x << (32 - n))

/** SHA-256 of the UTF-8 bytes of `text`, as 64 lowercase hex characters. */
export function sha256Hex(text: string): string {
  const bytes = new TextEncoder().encode(text)
  const padded = new Uint8Array((((bytes.length + 9 + 63) >> 6) << 6))
  padded.set(bytes)
  padded[bytes.length] = 0x80
  const view = new DataView(padded.buffer)
  const bits = bytes.length * 8
  view.setUint32(padded.length - 8, Math.floor(bits / 0x100000000))
  view.setUint32(padded.length - 4, bits >>> 0)
  const h = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]
  const w = new Uint32Array(64)
  for (let off = 0; off < padded.length; off += 64) {
    for (let i = 0; i < 16; i++) w[i] = view.getUint32(off + i * 4)
    for (let i = 16; i < 64; i++) {
      const a = w[i - 15]!
      const b = w[i - 2]!
      const s0 = rotr(a, 7) ^ rotr(a, 18) ^ (a >>> 3)
      const s1 = rotr(b, 17) ^ rotr(b, 19) ^ (b >>> 10)
      w[i] = (w[i - 16]! + s0 + w[i - 7]! + s1) >>> 0
    }
    let [a, b, c, d, e, f, g, hh] = h as [number, number, number, number, number, number, number, number]
    for (let i = 0; i < 64; i++) {
      const t1 = (hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[i]! + w[i]!) >>> 0
      const t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) >>> 0
      hh = g
      g = f
      f = e
      e = (d + t1) >>> 0
      d = c
      c = b
      b = a
      a = (t1 + t2) >>> 0
    }
    const out = [a, b, c, d, e, f, g, hh]
    for (let i = 0; i < 8; i++) h[i] = (h[i]! + out[i]!) >>> 0
  }
  return h.map((x) => x.toString(16).padStart(8, '0')).join('')
}

/** JSON with sorted keys and no whitespace, characters unescaped: Python's `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. */
export function canonical(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value) ?? 'null'
  if (Array.isArray(value)) return `[${value.map((v) => (v === undefined ? 'null' : canonical(v))).join(',')}]`
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([, v]) => v !== undefined)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
  return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(',')}}`
}

export const digest = (value: unknown): string => sha256Hex(canonical(value))

export const ZERO_HASH = '0'.repeat(64)

const linkHash = (prevHash: string, e: Pick<ChainEvent, 'seq' | 'type' | 'at' | 'data'>): string =>
  sha256Hex(`${prevHash}\n${canonical({ seq: e.seq, type: e.type, at: e.at, data: e.data })}`)

/** `b` with one more event: in the same update as the change it records. */
export function withEvent(b: Briefing, type: ChainEventType, data: Record<string, unknown>, at = new Date().toISOString()): Briefing {
  const events = b.events ?? []
  const prevHash = events[events.length - 1]?.hash ?? ZERO_HASH
  const seq = events.length + 1
  const event: ChainEvent = { seq, type, at, data, prevHash, hash: linkHash(prevHash, { seq, type, at, data }) }
  return { ...b, events: [...events, event], recordHash: event.hash }
}

/** The bound digest an event claims against what the record holds now: null, or the backend's reason code. */
function boundMismatch(b: Briefing, e: ChainEvent, latestOf: (type: ChainEventType, n?: number) => ChainEvent | undefined): string | null {
  const round = typeof e.data.n === 'number' ? b.rounds.find((r) => r.n === e.data.n) : undefined
  switch (e.type) {
    case 'steps_confirmed':
      if (latestOf('steps_confirmed') !== e) return null
      return e.data.stepsSha256 === digest(b.steps) ? null : 'steps_mismatch'
    case 'round_created':
    case 'script_approved':
      if (!round || latestOf(e.type, round.n) !== e) return null
      return e.data.scriptSha256 === digest(round.script) ? null : 'script_mismatch'
    case 'round_judged':
      if (!round) return 'round_missing'
      return e.data.ratingsSha256 === digest(round.ratings) ? null : 'ratings_mismatch'
    case 'decided': {
      const d = b.decision
      if (!d) return 'decision_mismatch'
      const reason = d.reason ? sha256Hex(d.reason) : null
      // 2026-10-17: the event holds `inPerson: true` only for an in-person check, and binds it.
      const inPerson = (e.data.inPerson ?? null) === (d.inPerson ? true : null)
      return e.data.value === d.value && e.data.reasonSha256 === reason && inPerson ? null : 'decision_mismatch'
    }
    default:
      return null
  }
}

/** Endpoint 25: every link recomputed in order, then every bound digest against the record as it is stored now. */
export function verifyChain(b: Briefing): VerifyResult {
  const events = b.events ?? []
  if (events.length === 0) return { ok: false, events: 0, recordHash: '', reason: 'no_chain' }
  let prev = ZERO_HASH
  for (const e of events) {
    if (e.prevHash !== prev || linkHash(prev, e) !== e.hash) return { ok: false, events: events.length, recordHash: b.recordHash ?? '', brokenAt: e.seq, reason: e.prevHash !== prev ? 'prev_hash_mismatch' : 'hash_mismatch' }
    prev = e.hash
  }
  const latestOf = (type: ChainEventType, n?: number) => [...events].reverse().find((x) => x.type === type && (n === undefined || x.data.n === n))
  for (const e of events) {
    const reason = boundMismatch(b, e, latestOf)
    if (reason) return { ok: false, events: events.length, recordHash: b.recordHash ?? '', brokenAt: e.seq, reason }
  }
  if ((b.recordHash ?? '') !== (events[events.length - 1]?.hash ?? '')) return { ok: false, events: events.length, recordHash: b.recordHash ?? '', brokenAt: events.length, reason: 'record_hash_mismatch' }
  return { ok: true, events: events.length, recordHash: b.recordHash ?? '' }
}
