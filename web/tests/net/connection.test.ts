import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { signalHint, signalQuality, watchSignal } from '../../src/net/connection.ts'
import { signalCopy } from '../../src/net/signalCopy.ts'

// 2026-10-16 signal: the handover step's hint ("Weak signal: Turn by turn works better") comes from navigator.connection when the
// browser has it, and never blocks anything; the check's wait shows a calm banner in the supervisor's language with the time waited.

describe('signalQuality', () => {
  it('offline when the phone says so, whatever the connection type', () => {
    assert.equal(signalQuality({ onLine: false, connection: { effectiveType: '4g' } }), 'offline')
  })

  it('weak on 2G and 3G, ok on 4G', () => {
    for (const type of ['slow-2g', '2g', '3g']) assert.equal(signalQuality({ onLine: true, connection: { effectiveType: type } }), 'weak')
    assert.equal(signalQuality({ onLine: true, connection: { effectiveType: '4g' } }), 'ok')
  })

  it('unknown where the browser does not say (Safari, Firefox) or outside a browser', () => {
    assert.equal(signalQuality({ onLine: true }), 'unknown')
    assert.equal(signalQuality({ onLine: true, connection: {} }), 'unknown')
    assert.equal(signalQuality(undefined), 'unknown')
  })
})

describe('signalHint (the handover step)', () => {
  it('suggests Turn by turn on a weak signal while Live is chosen', () => {
    assert.equal(signalHint('weak', 'live'), 'signal.hintWeak')
    assert.equal(signalHint('weak', 'turn'), null)
  })

  it('says a briefing needs a signal when there is none, and nothing otherwise', () => {
    assert.equal(signalHint('offline', 'live'), 'signal.hintOffline')
    assert.equal(signalHint('offline', 'turn'), 'signal.hintOffline')
    for (const q of ['ok', 'unknown'] as const) for (const m of ['live', 'turn'] as const) assert.equal(signalHint(q, m), null)
  })
})

describe('watchSignal', () => {
  it('listens for online, offline and connection changes, and stops on unsubscribe', () => {
    const added: string[] = []
    const removed: string[] = []
    const target = { addEventListener: (t: string) => added.push(t), removeEventListener: (t: string) => removed.push(t) }
    const connection = { effectiveType: '4g', addEventListener: (t: 'change') => added.push(`connection:${t}`), removeEventListener: (t: 'change') => removed.push(`connection:${t}`) }
    const stop = watchSignal(() => undefined, target as never, { connection })
    assert.deepEqual(added, ['online', 'offline', 'connection:change'])
    stop()
    assert.deepEqual(removed, ['online', 'offline', 'connection:change'])
  })
})

describe('the no-signal banner copy', () => {
  it('says the answers are kept and how long it has waited, in the supervisor language', () => {
    const { title, body } = signalCopy({ since: 0, failures: 3, offline: true }, 65_000, 'en')
    assert.equal(title, 'No signal')
    assert.equal(body, 'The answers are kept on this phone and sent when the signal is back. Time waited: 1:05')
  })

  it('names a dropped connection when the phone still says it is online', () => {
    assert.equal(signalCopy({ since: 0, failures: 1, offline: false }, 0, 'en').title, 'The connection dropped')
  })

  it('Tamil and Chinese have their own copy, and Chinese sentences join with no space', () => {
    const ta = signalCopy({ since: 0, failures: 1, offline: true }, 5_000, 'ta')
    const zh = signalCopy({ since: 0, failures: 1, offline: true }, 5_000, 'zh')
    assert.match(ta.body, /0:05/)
    assert.doesNotMatch(ta.body, /answers/)
    assert.match(zh.body, /发送。已等待 0:05$/)
  })

  it('never shows a negative time when the clock moves back', () => {
    assert.match(signalCopy({ since: 10_000, failures: 1, offline: true }, 0, 'en').body, /0:00$/)
  })
})
