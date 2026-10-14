import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { resolveWsUrl } from '../../src/live/liveUrl.ts'

const http = { protocol: 'http:', host: 'localhost:5173' }
const https = { protocol: 'https:', host: 'say-it-back.web.app' }

describe('resolveWsUrl', () => {
  it('uses an absolute ws(s) URL exactly as given (the Cloud Run URL)', () => {
    assert.equal(resolveWsUrl('wss://say-it-back-api-x.a.run.app/api/live/b_1/1', https), 'wss://say-it-back-api-x.a.run.app/api/live/b_1/1')
    assert.equal(resolveWsUrl('ws://127.0.0.1:8080/api/live/b_1/1', http), 'ws://127.0.0.1:8080/api/live/b_1/1')
  })

  it('maps an absolute http(s) URL to ws(s)', () => {
    assert.equal(resolveWsUrl('https://api.example.com/api/live/b_1/1', http), 'wss://api.example.com/api/live/b_1/1')
    assert.equal(resolveWsUrl('http://localhost:8080/api/live/b_1/1', https), 'ws://localhost:8080/api/live/b_1/1')
  })

  it('turns a same-origin path into ws(s)://host/path by the page protocol', () => {
    assert.equal(resolveWsUrl('/api/live/b_1/1', http), 'ws://localhost:5173/api/live/b_1/1')
    assert.equal(resolveWsUrl('/api/live/b_1/1', https), 'wss://say-it-back.web.app/api/live/b_1/1')
  })

  it('tolerates a path without the leading slash', () => {
    assert.equal(resolveWsUrl('api/live/b_1/1', http), 'ws://localhost:5173/api/live/b_1/1')
  })
})
