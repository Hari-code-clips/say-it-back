import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { createUploadQueue, MAX_AGE_MS, memoryStore, newUploadKey, uploadId, type PendingUpload, type UploadStore } from '../../src/net/queue.ts'

// 2026-10-16 signal: the worker's answers stay on the phone from the last answer until their check has an answer, then are deleted;
// never longer than a day. The server accepts an Idempotency-Key of 16 to 64 characters of A-Z a-z 0-9 _ - (backend idempotency.py).

const SERVER_KEY = /^[A-Za-z0-9_-]{16,64}$/

const job = (over: Partial<PendingUpload> = {}): PendingUpload => ({
  briefingId: 'b_aaaaaaaaaaaa',
  n: 1,
  key: 'Kq3vX9_tY2-pLm8RwZ4sNa',
  mode: 'live',
  sampleAnswers: [],
  clips: { q1: new Blob([new Uint8Array([1, 2, 3])], { type: 'audio/wav' }) },
  savedAt: 1_000,
  ...over,
})

function broken(): UploadStore {
  const fail = async () => {
    throw new Error('QuotaExceededError')
  }
  return { get: fail, put: fail, delete: fail, all: fail }
}

describe('the upload queue', () => {
  it('keeps a job until it is dropped, keyed by briefing and round', async () => {
    const q = createUploadQueue(memoryStore(), () => 2_000)
    await q.save(job())
    await q.save(job({ n: 2, key: 'another-key-0123456789' }))

    assert.equal((await q.load('b_aaaaaaaaaaaa', 1))?.key, 'Kq3vX9_tY2-pLm8RwZ4sNa')
    assert.equal((await q.load('b_aaaaaaaaaaaa', 2))?.n, 2)
    await q.drop('b_aaaaaaaaaaaa', 1)
    assert.equal(await q.load('b_aaaaaaaaaaaa', 1), undefined)
    assert.equal((await q.load('b_aaaaaaaaaaaa', 2))?.n, 2)
  })

  it('keeps the clips themselves (the Blob), not a copy of their names', async () => {
    const q = createUploadQueue(memoryStore(), () => 2_000)
    await q.save(job())
    const clip = (await q.load('b_aaaaaaaaaaaa', 1))?.clips.q1
    assert.deepEqual([...new Uint8Array(await clip!.arrayBuffer())], [1, 2, 3])
  })

  it('never hands back, and deletes, a job older than a day', async () => {
    const store = memoryStore()
    let now = 1_000
    const q = createUploadQueue(store, () => now)
    await q.save(job())
    now = 1_000 + MAX_AGE_MS
    assert.equal(await q.load('b_aaaaaaaaaaaa', 1), undefined)
    assert.equal(await store.get(uploadId('b_aaaaaaaaaaaa', 1)), undefined)
  })

  it('sweep deletes only the old jobs', async () => {
    const store = memoryStore()
    const q = createUploadQueue(store, () => MAX_AGE_MS + 5_000)
    await q.save(job({ savedAt: 1_000 }))
    await q.save(job({ n: 2, savedAt: MAX_AGE_MS + 4_000 }))
    await q.sweep()
    assert.deepEqual((await store.all()).map((j) => j.n), [2])
  })

  it('a recorded decision deletes every round of that briefing, and only that briefing', async () => {
    const store = memoryStore()
    const q = createUploadQueue(store, () => 2_000)
    await q.save(job())
    await q.save(job({ n: 2 }))
    await q.save(job({ briefingId: 'b_bbbbbbbbbbbb' }))
    await q.dropBriefing('b_aaaaaaaaaaaa')
    assert.deepEqual((await store.all()).map((j) => j.briefingId), ['b_bbbbbbbbbbbb'])
  })

  it('falls back to memory when IndexedDB refuses, and the round is still kept', async () => {
    const q = createUploadQueue(broken(), () => 2_000)
    await q.save(job())
    assert.equal(q.inMemory(), true)
    assert.equal((await q.load('b_aaaaaaaaaaaa', 1))?.key, 'Kq3vX9_tY2-pLm8RwZ4sNa')
  })

  it('never throws into the briefing, whatever the store does', async () => {
    const q = createUploadQueue(broken(), () => 2_000)
    await q.drop('b_aaaaaaaaaaaa', 1)
    await q.sweep()
    assert.equal(await q.load('b_aaaaaaaaaaaa', 9), undefined)
  })
})

describe('newUploadKey', () => {
  it('is 128 random bits in a form the server accepts', () => {
    const key = newUploadKey()
    assert.match(key, SERVER_KEY)
    assert.equal(key.length, 22)
  })

  it('maps every byte value into the allowed letters (base64url, no padding)', () => {
    for (const fill of [0x00, 0xff, 0xfb, 0x3e, 0x3f]) {
      assert.match(newUploadKey((b) => b.fill(fill)), SERVER_KEY)
    }
  })

  it('is different every time', () => {
    const keys = new Set(Array.from({ length: 200 }, () => newUploadKey()))
    assert.equal(keys.size, 200)
  })
})
