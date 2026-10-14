import { ApiError } from '../api/transport.ts'
import type { Translate } from '../i18n/index.tsx'
import { errorTextKey } from './errorCodes.ts'

/**
 * User-facing text for a failed API call. Transport failures and bare 5xx responses get a localised
 * message (not "Bad Gateway"); the common structured errors are localised by code; the rest keep
 * the backend's own human-readable message.
 */
export function apiErrorText(t: Translate, e: unknown): string {
  if (!(e instanceof ApiError)) return t('error.generic')
  if (e.code === 'network') return t('error.network')
  if (e.code === 'timeout') return t('error.timeout')
  if (e.status >= 500 && e.code.startsWith('http_')) return t('error.server')
  const key = errorTextKey(e.code)
  if (key) return t(key)
  return e.message || t('error.generic')
}
