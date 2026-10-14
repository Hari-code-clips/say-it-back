import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { Lang } from '../api/types.ts'
import { en } from './en.ts'
import { LANG_NAMES } from './langNames.ts'
import { ta } from './ta.ts'
import { zh } from './zh.ts'

// UI strings follow the supervisor's language: English, Tamil and Chinese (the supervisor
// languages of the two sites). Worker-language text comes from the backend; the few static
// worker-screen words live in worker.ts.

export type UiLang = 'en' | 'ta' | 'zh'
export type StringKey = keyof typeof en
export type Translate = (key: StringKey, vars?: Record<string, string | number>) => string

export const UI_LANGS: readonly UiLang[] = ['en', 'ta', 'zh']
const TABLES: Record<UiLang, Record<StringKey, string>> = { en, ta, zh }
const STORAGE_KEY = 'sib.uiLang'

/** Any contract language -> the nearest UI language (English when there is no table). */
export function asUiLang(lang: string | undefined): UiLang {
  return lang === 'ta' || lang === 'zh' ? lang : 'en'
}

function initialLang(): UiLang {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'en' || stored === 'ta' || stored === 'zh') return stored
  } catch {
    /* storage unavailable */
  }
  const nav = (navigator.language || 'en').slice(0, 2)
  return asUiLang(nav)
}

export function translate(lang: UiLang, key: StringKey, vars?: Record<string, string | number>): string {
  const raw = TABLES[lang][key] ?? en[key]
  if (!vars) return raw
  return raw.replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? `{${name}}`))
}

interface I18nValue {
  lang: UiLang
  setLang: (lang: UiLang) => void
  t: Translate
}

const I18nContext = createContext<I18nValue | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<UiLang>(initialLang)

  const setLang = useCallback((next: UiLang) => {
    setLangState(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* storage unavailable */
    }
  }, [])

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  const value = useMemo<I18nValue>(() => ({ lang, setLang, t: (key, vars) => translate(lang, key, vars) }), [lang, setLang])
  return <I18nContext value={value}>{children}</I18nContext>
}

function useI18n(): I18nValue {
  const v = useContext(I18nContext)
  if (!v) throw new Error('I18nProvider is missing')
  return v
}

export const useT = (): Translate => useI18n().t
export const useUiLang = (): { lang: UiLang; setLang: (lang: UiLang) => void } => {
  const { lang, setLang } = useI18n()
  return { lang, setLang }
}

/** "SOP-EL-04 v3"; a pasted SOP (id CUSTOM) reads as "Custom SOP". */
export const useSopLabel = (): ((sop: { id: string; version: string }) => string) => {
  const t = useT()
  return (sop) => (sop.id === 'CUSTOM' ? t('start.custom.short') : `${sop.id} ${sop.version}`)
}

/** Language names in the UI language: "Tamil", "தமிழ்" or "泰米尔语" for `ta`. */
export const useLangName = (): ((lang: Lang) => string) => {
  const { lang } = useI18n()
  return (code) => LANG_NAMES[lang][code]
}
