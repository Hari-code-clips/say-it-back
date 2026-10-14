import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { parseServerMessage } from '../../src/live/protocol.ts'

describe('parseServerMessage', () => {
  it('parses each server frame of the contract', () => {
    assert.deepEqual(parseServerMessage('{"type":"ready","model":"m","turnTaking":"manual"}'), { type: 'ready', model: 'm', turnTaking: 'manual' })
    assert.deepEqual(parseServerMessage('{"type":"caption","role":"worker","text":"hi","final":true}'), { type: 'caption', role: 'worker', text: 'hi', final: true })
    assert.deepEqual(parseServerMessage('{"type":"turn_complete"}'), { type: 'turn_complete' })
    assert.deepEqual(parseServerMessage('{"type":"interrupted"}'), { type: 'interrupted' })
    assert.deepEqual(parseServerMessage('{"type":"error","code":"limit","message":"too long"}'), { type: 'error', code: 'limit', message: 'too long' })
  })

  it('treats a missing `final` as a partial caption', () => {
    assert.deepEqual(parseServerMessage('{"type":"caption","role":"model","text":"x"}'), { type: 'caption', role: 'model', text: 'x', final: false })
  })

  it('gives an error frame without a code the code "unknown"', () => {
    assert.deepEqual(parseServerMessage('{"type":"error"}'), { type: 'error', code: 'unknown', message: '' })
  })

  it('ignores malformed, unknown or invalid frames', () => {
    assert.equal(parseServerMessage('not json'), null)
    assert.equal(parseServerMessage('{"type":"something_new"}'), null)
    assert.equal(parseServerMessage('{"type":"ready","model":"m","turnTaking":"turbo"}'), null)
    assert.equal(parseServerMessage('{"type":"caption","role":"bot","text":"x"}'), null)
    assert.equal(parseServerMessage('42'), null)
    assert.equal(parseServerMessage('null'), null)
  })
})
