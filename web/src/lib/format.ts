// Dates and times in the UI language. Singapore and Chennai both use English, so `en` formats as en-SG.
const LOCALES: Record<string, string> = { en: 'en-SG', ta: 'ta-IN', zh: 'zh-CN' }
const localeOf = (lang: string): string => LOCALES[lang] ?? lang

/** e.g. "13 Oct 2026, 1:22 pm". Falls back to the raw string when the date is invalid. */
export function formatDateTime(iso: string, lang: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return new Intl.DateTimeFormat(localeOf(lang), { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

export function formatDate(iso: string, lang: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return new Intl.DateTimeFormat(localeOf(lang), { dateStyle: 'medium' }).format(date)
}

/** e.g. "1:22:05 pm": a compact time for a list of events on one day. */
export function formatTime(iso: string, lang: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return new Intl.DateTimeFormat(localeOf(lang), { timeStyle: 'medium' }).format(date)
}
