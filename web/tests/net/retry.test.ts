import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { ApiError } from '../../src/api/transport.ts'
import { backoffDelay, unreachable, untilAnswered, UPLOAD_BACKOFF, type RetryDeps, type Waiting } from '../../src/net/retry.ts'

// 2026-10-16 signal: the check upload is sent again by itself only when no answer came back (offline, a dropped connection, a
// timeout), with exponential backoff and jitter. Any reply the server gave, 4xx or 5xx, is final.

const network = () => new ApiError(0, 'network', 'Could not reach the server.')
const timeout = () => new ApiError(0, 'timeout', 'The server took too long to answer.')

function fakeDeps(online = false): RetryDeps & { pauses: number[]; clock: number } {
  const deps = {
    pauses: [] as number[],
    clock: 1_000,
    now: () => deps.clock,
    online: () => online,
    random: () => 0.5,
    pause: async (ms: number, signal?: AbortSignal) => {
      if (signal?.aborted) throw new Error('aborted')
      deps.pauses.push(ms)
      deps.clock += ms
    },
  }
  return deps
}

/** A send that fails with `errors` in turn, then answers `answer`. */
function flaky<T>(errors: unknown[], answer: T) {
  const calls = { n: 0 }
  const send = async () => {
    const e = errors[calls.n++]
    if (e !== undefined) throw e
    return answer
  }
  return { send, calls }
}

describe('backoffDelay', () => {
  it('doubles from the base up to the cap, with half of each step random', () => {
    const half = [0, 1, 2, 3, 4, 5, 6].map((n) => backoffDelay(n, UPLOAD_BACKOFF, () => 0))
    assert.deepEqual(half, [500, 1_000, 2_000, 4_000, 8_000, 15_000, 15_000])
    const full = [0, 1, 6, 40].map((n) => backoffDelay(n, UPLOAD_BACKOFF, () => 1))
    assert.deepEqual(full, [1_000, 2_000, 30_000, 30_000])
  })

  it('is never zero, never above the cap, and spreads phones over the step', () => {
    for (let n = 0; n < 12; n++) {
      for (const r of [0, 0.3, 0.999, 1, -1, 2]) {
        const d = backoffDelay(n, UPLOAD_BACKOFF, () => r)
        assert.ok(d >= 500 && d <= 30_000, `attempt ${n}, random ${r}: ${d}`)
      }
    }
    assert.notEqual(backoffDelay(3, UPLOAD_BACKOFF, () => 0.1), backoffDelay(3, UPLOAD_BACKOFF, () => 0.9))
  })
})

describe('unreachable: only an answer that never came back is sent again', () => {
  it('network and timeout failures', () => {
    assert.equal(unreachable(network()), true)
    assert.equal(unreachable(timeout()), true)
  })

  it('never a reply the server gave, and never anything else', () => {
    for (const [status, code] of [[400, 'validation_error'], [409, 'invalid_state'], [409, 'check_in_progress'], [413, 'payload_too_large'], [422, 'invalid_audio'], [429, 'daily_limit'], [500, 'internal_error'], [502, 'upstream_error'], [503, 'upstream_busy']] as const) {
      assert.equal(unreachable(new ApiError(status, code, 'x')), false, `${status} ${code}`)
    }
    assert.equal(unreachable(new Error('network')), false)
    assert.equal(unreachable(new ApiError(0, 'aborted', 'x')), false)
  })
})

describe('untilAnswered', () => {
  it('sends again after each dropped connection and returns the answer', async () => {
    const deps = fakeDeps()
    const { send, calls } = flaky([network(), timeout(), network()], 'judged')
    const seen: (Waiting | null)[] = []

    const answer = await untilAnswered(send, { deps, onWait: (w) => seen.push(w) })

    assert.equal(answer, 'judged')
    assert.equal(calls.n, 4)
    assert.deepEqual(deps.pauses, [750, 1_500, 3_000])
    assert.deepEqual(seen, [
      { since: 1_000, failures: 1, offline: true },
      { since: 1_000, failures: 2, offline: true },
      { since: 1_000, failures: 3, offline: true },
      null,
    ])
  })

  it('reports online when the phone says it is (the server was still unreachable)', async () => {
    const seen: (Waiting | null)[] = []
    await untilAnswered(flaky([network()], 1).send, { deps: fakeDeps(true), onWait: (w) => seen.push(w) })
    assert.equal(seen[0]?.offline, false)
  })

  for (const e of [new ApiError(409, 'invalid_state', 'judged'), new ApiError(422, 'validation_error', 'x'), new ApiError(429, 'daily_limit', 'x'), new ApiError(503, 'upstream_busy', 'x')]) {
    it(`never sends again after a ${e.status} ${e.code}`, async () => {
      const deps = fakeDeps()
      const { send, calls } = flaky([e], 'never')
      await assert.rejects(untilAnswered(send, { deps }), (thrown) => thrown === e)
      assert.equal(calls.n, 1)
      assert.deepEqual(deps.pauses, [])
    })
  }

  it('a reply after some dropped tries is final too, and the wait is cleared', async () => {
    const refused = new ApiError(409, 'invalid_state', 'judged')
    const seen: (Waiting | null)[] = []
    const { send, calls } = flaky([network(), refused], 'never')
    await assert.rejects(untilAnswered(send, { deps: fakeDeps(), onWait: (w) => seen.push(w) }), (thrown) => thrown === refused)
    assert.equal(calls.n, 2)
    assert.equal(seen.at(-1), null)
  })

  it('stops when the screen is left', async () => {
    const stop = new AbortController()
    const deps = fakeDeps()
    let n = 0
    const send = async () => {
      if (++n === 2) stop.abort()
      throw network()
    }
    await assert.rejects(untilAnswered(send, { deps, signal: stop.signal }))
    assert.equal(n, 2)
  })

  it('says nothing when the first try is answered', async () => {
    const seen: (Waiting | null)[] = []
    assert.equal(await untilAnswered(async () => 'ok', { deps: fakeDeps(), onWait: (w) => seen.push(w) }), 'ok')
    assert.deepEqual(seen, [])
  })
})
