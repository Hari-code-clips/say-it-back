// Live session protocol (docs/API.md, "Live session protocol"). Text frames are JSON;
// binary frames are raw PCM16 little-endian mono (16 kHz up, 24 kHz down).

export type Cue = { cue: 'READ_INSTRUCTION' } | { cue: 'CLOSE' } | { cue: 'ASK'; qid: string }

export type ClientMessage =
  | { type: 'start'; ticket: string }
  | ({ type: 'cue' } & Cue)
  | { type: 'answer_start'; qid: string }
  | { type: 'answer_end'; qid: string }
  | { type: 'stop' }

export type ServerMessage =
  | { type: 'ready'; model: string; turnTaking: 'manual' | 'auto' }
  | { type: 'caption'; role: 'model' | 'worker'; text: string; final: boolean }
  | { type: 'turn_complete' }
  | { type: 'interrupted' }
  | { type: 'error'; code: string; message: string }

/** Contract limit: binary frames are at most 8 KB (mic frames are 640 bytes). */
export const MAX_BINARY_FRAME = 8192

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null

/** Parses one server text frame; anything malformed or unknown is ignored (null). */
export function parseServerMessage(raw: string): ServerMessage | null {
  let m: unknown
  try {
    m = JSON.parse(raw)
  } catch {
    return null
  }
  if (!isObject(m) || typeof m.type !== 'string') return null
  switch (m.type) {
    case 'ready':
      return typeof m.model === 'string' && (m.turnTaking === 'manual' || m.turnTaking === 'auto')
        ? { type: 'ready', model: m.model, turnTaking: m.turnTaking }
        : null
    case 'caption':
      return (m.role === 'model' || m.role === 'worker') && typeof m.text === 'string'
        ? { type: 'caption', role: m.role, text: m.text, final: m.final === true }
        : null
    case 'turn_complete':
      return { type: 'turn_complete' }
    case 'interrupted':
      return { type: 'interrupted' }
    case 'error':
      return {
        type: 'error',
        code: typeof m.code === 'string' ? m.code : 'unknown',
        message: typeof m.message === 'string' ? m.message : '',
      }
    default:
      return null
  }
}
