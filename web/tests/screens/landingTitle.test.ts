import assert from 'node:assert/strict'
import { after, describe, it } from 'node:test'
import type { ComponentType } from 'react'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import { createElement, html, startSsr } from '../helpers/ssr.ts'

// Colour system v2 (web/design.md): the landing headline asks in ink and answers in the action blue, as the deck's titles do.
const ssr = await startSsr()
after(() => ssr.close())
const { TitleLines } = await ssr.load<Record<'TitleLines', ComponentType<{ text: string }>>>('/src/screens/LandingScreen.tsx')

const render = (text: string) => html(createElement(TitleLines, { text }))
const blue = (markup: string) => /<span class="text-primary">([^<]*)<\/span>/.exec(markup)?.[1]

describe('the landing headline: the question in ink, the answer in blue', () => {
  for (const [lang, table] of [['en', en], ['ta', ta], ['zh', zh]] as const) {
    it(`${lang}: the part after the first question mark is the blue answer, and no word is lost`, () => {
      const title = (table as Record<string, string>)['landing.title'] ?? ''
      const markup = render(title)
      const answer = blue(markup)
      assert.ok(answer, `${lang}: no blue answer in ${markup}`)
      assert.ok(title.endsWith(answer), `${lang}: the answer is the end of the title`)
      assert.equal(markup.replace(/<[^>]+>/g, '').replace(/\s+/g, ''), title.replace(/\s+/g, ''))
    })
  }

  it('leaves a title without a question (or ending on one) as a single ink line', () => {
    assert.equal(blue(render('Hear it back before work starts.')), undefined)
    assert.equal(blue(render('Did they understand?')), undefined)
  })
})
