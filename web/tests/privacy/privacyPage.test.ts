import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { after, describe, it } from 'node:test'
import type { ComponentType } from 'react'
import { Router } from 'wouter'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import { createElement, html, startSsr, visibleText, withUiLang } from '../helpers/ssr.ts'

// Privacy, 16 Oct: the /privacy page (supervisor language), linked from About and the landing footer line. Honest: "designed to support",
// never "compliant"; no legal claim.

type Props = Record<string, unknown>
const ssr = await startSsr()
after(() => ssr.close())
const { I18nProvider } = await ssr.load<{ I18nProvider: ComponentType<Props> }>('/src/i18n/index.tsx')
const { CatalogProvider } = await ssr.load<{ CatalogProvider: ComponentType<Props> }>('/src/api/catalog.tsx')
const { FeedbackProvider } = await ssr.load<{ FeedbackProvider: ComponentType<Props> }>('/src/ui/FeedbackProvider.tsx')
const { PrivacyArticle, PRIVACY_SECTIONS } = await ssr.load<{ PrivacyArticle: ComponentType; PRIVACY_SECTIONS: { id: string; title: string; body: string[] }[] }>(
  '/src/screens/PrivacyScreen.tsx',
)

const page = (lang: 'en' | 'ta' | 'zh') =>
  withUiLang(lang, () =>
    html(
      createElement(Router, {
        ssrPath: '/privacy',
        children: createElement(I18nProvider, null, createElement(CatalogProvider, null, createElement(FeedbackProvider, null, createElement(PrivacyArticle)))),
      }),
    ),
  )

const src = (path: string) => readFileSync(new URL(`../../src/${path}`, import.meta.url), 'utf8')
const T = en as Record<string, string>

describe('the privacy page', () => {
  const markup = page('en')
  const text = visibleText(markup)

  it('covers what is collected, where, how long, deletion, consent, and the two laws, in that order', () => {
    assert.deepEqual(PRIVACY_SECTIONS.map((s) => s.id), ['collect', 'where', 'keep', 'delete', 'consent', 'law'])
    let at = -1
    for (const s of PRIVACY_SECTIONS) {
      const found = text.indexOf(T[s.title] ?? '?', at + 1) // the law's title is also in the subtitle: search on from the last one
      assert.ok(found > at, `${s.id} is missing or out of order`)
      at = found
      for (const key of s.body) assert.ok(text.includes(T[key] ?? '?'), `${key} is not on the page`)
    }
  })

  it('says what is never collected, that audio is not kept, and the retention default', () => {
    assert.match(T['privacy.collect.never'] ?? '', /name, ID number, nationality or score/)
    assert.match(T['privacy.collect.audio'] ?? '', /not kept/)
    // The phone holds an answer until its check answers (the signal builder's store), never more than a day, and sends it once.
    assert.match(T['privacy.collect.audio'] ?? '', /on this phone and sent once/)
    assert.match(T['privacy.collect.audio'] ?? '', /never more than a day/)
    assert.match(T['privacy.keep.body'] ?? '', /\b90\b/)
  })

  it('names where data is processed: the region, the global endpoint, Live in the US (us-central1), and that it is a transfer', () => {
    assert.match(T['privacy.where.body'] ?? '', /own Google Cloud region/)
    assert.match(T['privacy.where.body'] ?? '', /global endpoint/)
    assert.match(T['privacy.where.body'] ?? '', /Live, the live voice, runs in the US \(us-central1\)/) // 17 Oct, build-notes/37
    assert.match(T['privacy.where.transfer'] ?? '', /transfer/)
  })

  it('is honest about the law: "meant to support", no compliance claimed, not legal advice', () => {
    const all = Object.entries(T).filter(([k]) => k.startsWith('privacy.')).map(([, v]) => v).join(' ')
    assert.match(all, /PDPA/)
    assert.match(all, /DPDP/)
    assert.match(T['privacy.subtitle'] ?? '', /meant to support/)
    assert.match(T['privacy.subtitle'] ?? '', /claims no compliance/)
    assert.match(T['privacy.subtitle'] ?? '', /not legal advice/)
    // The only "compliance" word is the disclaimer itself; nothing says the product is compliant or certified.
    assert.doesNotMatch(all, /\bcompliant\b|\bcertified\b|\bguarantee/i)
  })

  it('says the webhook copy belongs to the system that received it', () => {
    assert.match(T['privacy.delete.body'] ?? '', /belongs to that system/)
  })

  it('renders in Tamil and Chinese with their own strings', () => {
    assert.ok(visibleText(page('ta')).includes(ta['privacy.title']))
    assert.ok(visibleText(page('zh')).includes(zh['privacy.title']))
  })

  it('is one Long Document column of at most 65 characters, headed by the page heading', () => {
    assert.match(markup, /max-w-\[65ch\]/)
    assert.equal((markup.match(/<h1\b/g) ?? []).length, 1)
    assert.equal((markup.match(/<h2\b/g) ?? []).length, PRIVACY_SECTIONS.length)
  })
})

describe('the page is reachable', () => {
  it('has a route', () => {
    assert.match(src('App.tsx'), /<Route path="\/privacy" component=\{PrivacyScreen\} \/>/)
  })

  it('is linked from About and from the landing footer line', () => {
    for (const file of ['screens/AboutScreen.tsx', 'screens/LandingScreen.tsx']) {
      assert.match(src(file), /<Link href="\/privacy"[^>]*>\s*\{t\('privacy\.link'\)\}/, file)
    }
  })

  it('the record offers deletion behind a confirm sheet', () => {
    assert.match(src('screens/RecordScreen.tsx'), /<DeleteRecord briefingId=\{b\.id\} \/>/)
    const del = src('screens/record/DeleteRecord.tsx')
    assert.match(del, /<Dialog/)
    assert.match(del, /api\.deleteBriefing\(briefingId\)/)
  })
})
