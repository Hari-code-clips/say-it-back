import assert from 'node:assert/strict'
import { after, describe, it } from 'node:test'
import type { ComponentType } from 'react'
import type { SampleChoice } from '../../src/screens/brief/sample.ts'
import { createElement, html, startSsr, visibleText, withUiLang } from '../helpers/ssr.ts'
import { defaultMode, liveListed } from '../../src/screens/brief/liveLanguages.ts'

// 17 Oct: Google's Live table lists no Mandarin, Burmese or Odia, so those briefings start turn by turn and say why;
// every other worker language starts in Live voice as before.
type Props = Record<string, unknown>
const ssr = await startSsr()
after(() => ssr.close())
const { I18nProvider } = await ssr.load<{ I18nProvider: ComponentType<Props> }>('/src/i18n/index.tsx')
const { HandoverForm } = await ssr.load<{ HandoverForm: ComponentType<Props> }>('/src/screens/brief/HandoverForm.tsx')

const none: SampleChoice = { kind: 'none' } as SampleChoice
const form = (listed: boolean, lang: 'en' | 'ta' | 'zh' = 'en') =>
  visibleText(
    withUiLang(lang, () =>
      html(createElement(I18nProvider, null, createElement(HandoverForm, { mode: listed ? 'live' : 'turn', onMode: () => undefined, sample: none, sampleOn: false, onSampleOn: () => undefined, workerName: 'Odia', liveListed: listed }))),
    ),
  )

describe('briefing mode by worker language (Google Live table, 2026-10-15)', () => {
  it('starts turn by turn for Mandarin, Burmese and Odia, and in Live voice for the rest', () => {
    for (const lang of ['zh', 'my', 'or']) assert.equal(defaultMode(lang), 'turn', lang)
    for (const lang of ['ta', 'bn', 'hi', 'te', 'en']) assert.equal(defaultMode(lang), 'live', lang)
    assert.equal(liveListed('or'), false)
  })

  it('says why on the handover, in every UI language, and only for an unlisted language', () => {
    assert.ok(form(false).includes('Google does not list Odia for live voice yet, so this briefing starts turn by turn.'), form(false))
    assert.ok(!form(true).includes('Google does not list'))
    for (const lang of ['ta', 'zh'] as const) assert.ok(form(false, lang).includes('Odia'), lang)
  })
})
