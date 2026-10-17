import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { ApiError, createTransport } from '../../src/api/transport.ts'
import { createDailyLimitWatch, isDailyLimit, retryFor } from '../../src/lib/dailyLimit.ts'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'

const fail = (status: number, code: string) =>
  new Response(JSON.stringify({ error: { code, message: 'x' } }), { status, headers: { 'Content-Type': 'application/json' } })

describe('the daily-limit watch', () => {
  it('starts not reached, and turns on for a 429 daily_limit only', () => {
    const watch = createDailyLimitWatch()

    watch.note(new ApiError(429, 'rate_limited', 'Too many requests.'))
    watch.note(new ApiError(503, 'upstream_busy', 'Busy.'))
    watch.note(new Error('daily_limit'))
    assert.equal(watch.reached(), false)

    watch.note(new ApiError(429, 'daily_limit', 'Daily limit reached.'))
    assert.equal(watch.reached(), true)
  })

  it('tells its listeners once, and not after they unsubscribe', () => {
    const watch = createDailyLimitWatch()
    let a = 0
    let b = 0
    watch.subscribe(() => a++)
    const stopB = watch.subscribe(() => b++)
    stopB()

    watch.note(new ApiError(429, 'daily_limit', ''))
    watch.note(new ApiError(429, 'daily_limit', ''))

    assert.deepEqual([a, b], [1, 0])
  })
})

describe('the transport tells the app of every failed call (onError)', () => {
  it('passes a 429 daily_limit to the watch, and still throws it to the caller', async () => {
    const watch = createDailyLimitWatch()
    const transport = createTransport({ base: '/api', deviceKey: () => 'k'.repeat(32), send: async () => fail(429, 'daily_limit'), onError: watch.note })

    await assert.rejects(transport.request('/briefings/b_1/steps/extract', { method: 'POST' }), (e: unknown) => e instanceof ApiError && e.code === 'daily_limit')
    assert.equal(watch.reached(), true)
  })

  it('reports transport failures too, and nothing for a call that succeeds', async () => {
    const seen: string[] = []
    let answer: () => Promise<Response> = async () => new Response('{}', { status: 200 })
    const transport = createTransport({ base: '/api', deviceKey: () => 'k'.repeat(32), send: () => answer(), onError: (e) => seen.push(e.code) })

    await transport.request('/catalog')
    answer = async () => {
      throw new TypeError('Failed to fetch')
    }
    await assert.rejects(transport.requestBlob('/export/briefings.csv'))

    assert.deepEqual(seen, ['network'])
  })
})

describe('no Retry on daily_limit: it cannot succeed before 00:00 UTC', () => {
  const retry = () => undefined

  it('offers Retry for any other failure', () => {
    for (const e of [new ApiError(503, 'upstream_busy', ''), new ApiError(429, 'rate_limited', ''), new ApiError(0, 'network', ''), new Error('x')]) {
      assert.deepEqual(retryFor(e, 'Retry', retry), { actionLabel: 'Retry', onAction: retry })
    }
  })

  it('offers none for daily_limit, so the snackbar has no action', () => {
    assert.equal(isDailyLimit(new ApiError(429, 'daily_limit', '')), true)
    assert.deepEqual(retryFor(new ApiError(429, 'daily_limit', ''), 'Retry', retry), {})
  })

  it('says when the budget comes back, in every UI language: 00:00 UTC, as the backend resets it', () => {
    for (const table of [en, ta, zh]) assert.match(table['demo.limitBody'], /00:00/)
  })
})
