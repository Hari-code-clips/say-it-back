import { en, type StringKey } from './en.ts'
import { ta } from './ta.ts'
import { zh } from './zh.ts'

// The string lookup without React, so pure helpers (src/lib/waitCopy.ts) can use it and run under node:test.
// index.tsx re-exports it with the provider and the hooks.

export type UiLang = 'en' | 'ta' | 'zh'

const TABLES: Record<UiLang, Record<StringKey, string>> = { en, ta, zh }

export function translate(lang: UiLang, key: StringKey, vars?: Record<string, string | number>): string {
  const raw = TABLES[lang][key] ?? en[key]
  if (!vars) return raw
  return raw.replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? `{${name}}`))
}
