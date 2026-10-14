import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { concatInt16, encodeWav, readWavInfo, wavBytes } from '../../src/audio/wav.ts'

describe('wavBytes', () => {
  it('writes a canonical 44-byte PCM header followed by little-endian samples', () => {
    const bytes = wavBytes(Int16Array.of(1, -2, 0x1234), 16_000)
    const view = new DataView(bytes.buffer)

    assert.equal(bytes.length, 44 + 6)
    assert.equal(String.fromCharCode(...bytes.subarray(0, 4)), 'RIFF')
    assert.equal(view.getUint32(4, true), 36 + 6)
    assert.equal(String.fromCharCode(...bytes.subarray(8, 16)), 'WAVEfmt ')
    assert.equal(view.getUint16(20, true), 1) // PCM
    assert.equal(view.getUint16(22, true), 1) // mono
    assert.equal(view.getUint32(24, true), 16_000)
    assert.equal(view.getUint32(28, true), 32_000) // byte rate
    assert.equal(view.getUint16(34, true), 16)
    assert.equal(String.fromCharCode(...bytes.subarray(36, 40)), 'data')
    assert.equal(view.getUint32(40, true), 6)
    assert.deepEqual([view.getInt16(44, true), view.getInt16(46, true), view.getInt16(48, true)], [1, -2, 0x1234])
  })

  it('handles an empty recording', () => {
    const bytes = wavBytes(new Int16Array(0))
    assert.equal(bytes.length, 44)
    assert.equal(readWavInfo(bytes)?.dataBytes, 0)
  })
})

describe('readWavInfo', () => {
  it('reads back what wavBytes wrote, including the duration', () => {
    const info = readWavInfo(wavBytes(new Int16Array(16_000), 16_000))
    assert.deepEqual(info, { sampleRate: 16_000, channels: 1, bitsPerSample: 16, dataBytes: 32_000, durationMs: 1000 })
  })

  it('returns null for anything that is not a canonical PCM WAV', () => {
    assert.equal(readWavInfo(new Uint8Array(10)), null)
    assert.equal(readWavInfo(new Uint8Array(64)), null)
  })
})

describe('encodeWav', () => {
  it('produces an audio/wav Blob of header + samples', () => {
    const blob = encodeWav(new Int16Array(320))
    assert.equal(blob.type, 'audio/wav')
    assert.equal(blob.size, 44 + 640)
  })
})

describe('concatInt16', () => {
  it('joins chunks in order', () => {
    assert.deepEqual([...concatInt16([Int16Array.of(1, 2), Int16Array.of(), Int16Array.of(3)])], [1, 2, 3])
  })
})
