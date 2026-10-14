// PCM16 mono <-> WAV. The mic delivers 16 kHz Int16 chunks; one WAV per answer goes to /check.

export const MIC_RATE = 16_000

export function concatInt16(chunks: readonly Int16Array[]): Int16Array {
  let total = 0
  for (const c of chunks) total += c.length
  const out = new Int16Array(total)
  let at = 0
  for (const c of chunks) {
    out.set(c, at)
    at += c.length
  }
  return out
}

const writeAscii = (view: DataView, offset: number, text: string) => {
  for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i))
}

/** 44-byte RIFF header + little-endian samples. Written with DataView, so it is endian-safe. */
export function wavBytes(pcm: Int16Array, sampleRate: number = MIC_RATE): Uint8Array<ArrayBuffer> {
  const dataLen = pcm.length * 2
  const bytes = new Uint8Array(44 + dataLen)
  const view = new DataView(bytes.buffer)
  writeAscii(view, 0, 'RIFF')
  view.setUint32(4, 36 + dataLen, true)
  writeAscii(view, 8, 'WAVE')
  writeAscii(view, 12, 'fmt ')
  view.setUint32(16, 16, true) // fmt chunk size
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true) // byte rate
  view.setUint16(32, 2, true) // block align
  view.setUint16(34, 16, true) // bits per sample
  writeAscii(view, 36, 'data')
  view.setUint32(40, dataLen, true)
  for (let i = 0; i < pcm.length; i++) view.setInt16(44 + i * 2, pcm[i] ?? 0, true)
  return bytes
}

export function encodeWav(pcm: Int16Array, sampleRate: number = MIC_RATE): Blob {
  return new Blob([wavBytes(pcm, sampleRate)], { type: 'audio/wav' })
}

export interface WavInfo {
  sampleRate: number
  channels: number
  bitsPerSample: number
  dataBytes: number
  durationMs: number
}

/** Reads a canonical PCM WAV header (used to check what we produced, and to size clips). */
export function readWavInfo(bytes: Uint8Array): WavInfo | null {
  if (bytes.length < 44) return null
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const tag = (o: number) => String.fromCharCode(view.getUint8(o), view.getUint8(o + 1), view.getUint8(o + 2), view.getUint8(o + 3))
  if (tag(0) !== 'RIFF' || tag(8) !== 'WAVE' || tag(12) !== 'fmt ') return null
  const channels = view.getUint16(22, true)
  const sampleRate = view.getUint32(24, true)
  const bitsPerSample = view.getUint16(34, true)
  if (tag(36) !== 'data') return null
  const dataBytes = view.getUint32(40, true)
  const frames = dataBytes / (channels * (bitsPerSample / 8))
  return { sampleRate, channels, bitsPerSample, dataBytes, durationMs: Math.round((frames / sampleRate) * 1000) }
}
