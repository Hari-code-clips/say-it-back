import type { StringKey } from '../i18n/en.ts'

/**
 * Backend error codes that have a localised sentence (docs/API.md, Deviations and "Daily cap"). Any other code
 * keeps the backend's own message. Kept apart from apiError.ts so it can be tested without the fetch client.
 */
export const CODE_TEXT: Readonly<Record<string, StringKey>> = {
  rate_limited: 'error.rate_limited',
  upstream_busy: 'error.upstream',
  upstream_error: 'error.upstream',
  payload_too_large: 'error.audio',
  audio_too_long: 'error.audio',
  invalid_audio: 'error.audio',
  unsupported_media_type: 'error.audio',
  live_not_recorded: 'error.live_not_recorded',
  limit: 'brief.err.limit',
  // The day's Gemini call budget is used up (429 with Retry-After until UTC midnight). Never "busy": nothing is wrong
  // with the service, and trying again today cannot work.
  daily_limit: 'error.daily_limit',
  // v0.3: the request carried no usable device key (401), or asked the voice for a line the round's script does not hold (422).
  device_required: 'error.device_required',
  tts_text_not_in_script: 'error.tts_text_not_in_script',
  // v0.4: the round's script was never confirmed (409); Go with a reported problem still open (409); an acknowledgement
  // with too short a note (422); the briefing holds the most problem reports it can (422); no stored sample answer (404).
  script_not_approved: 'error.script_not_approved',
  hazard_open: 'error.hazard_open',
  note_required: 'error.note_required',
  too_many_hazards: 'error.too_many_hazards',
  no_demo_answer: 'error.no_demo_answer',
  // 2026-10-16 signal: a retried upload's first try is still being checked on the server (409, Idempotency-Key).
  check_in_progress: 'signal.checkInProgress',
}

/** The i18n key for a backend error code, or undefined when the code has no localised sentence. */
export const errorTextKey = (code: string): StringKey | undefined => CODE_TEXT[code]
