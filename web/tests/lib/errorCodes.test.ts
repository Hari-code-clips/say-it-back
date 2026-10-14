import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import { ApiError } from '../../src/api/transport.ts'
import { apiErrorText } from '../../src/lib/apiError.ts'
import { CODE_TEXT, errorTextKey } from '../../src/lib/errorCodes.ts'

const tables = { en, ta, zh } as const

describe('errorTextKey', () => {
  it('maps the backend daily_limit code to its own sentence', () => {
    assert.equal(errorTextKey('daily_limit'), 'error.daily_limit')
  })

  it('says it in every UI language, and says "tomorrow"', () => {
    assert.match(en['error.daily_limit'], /tomorrow/i)
    assert.match(zh['error.daily_limit'], /明天/)
    assert.match(ta['error.daily_limit'], /நாளை/)
  })

  it('is not the "busy" or the "too many requests" sentence: nothing is wrong with the service, and waiting a few seconds will not help', () => {
    for (const [name, table] of Object.entries(tables)) {
      assert.notEqual(table['error.daily_limit'], table['error.upstream'], name)
      assert.notEqual(table['error.daily_limit'], table['error.rate_limited'], name)
      assert.notEqual(table['error.daily_limit'], table['brief.err.upstream_busy'], name)
    }
  })

  it('leaves unknown codes to the backend message', () => {
    assert.equal(errorTextKey('something_new'), undefined)
  })

  it('points every mapped code at a key that exists in all three tables', () => {
    for (const key of Object.values(CODE_TEXT)) {
      for (const [name, table] of Object.entries(tables)) assert.match((table as Record<string, string>)[key] ?? '', /\S/, `${name}: ${key}`)
    }
  })
})

describe('the v0.3 error codes', () => {
  const NEW = { device_required: 'error.device_required', tts_text_not_in_script: 'error.tts_text_not_in_script' } as const
  const say = (lang: keyof typeof tables) => (key: keyof typeof en) => tables[lang][key]

  it('map to their own sentences', () => {
    for (const [code, key] of Object.entries(NEW)) assert.equal(errorTextKey(code), key)
  })

  it('are said in English, Tamil and Chinese, each its own sentence and not the generic one', () => {
    for (const [name, table] of Object.entries(tables)) {
      const sentences = Object.values(NEW).map((key) => (table as Record<string, string>)[key] ?? '')
      assert.ok(sentences.every((s) => s.trim().length > 10), name)
      assert.equal(new Set([...sentences, (table as Record<string, string>)['error.generic']]).size, 3, name)
    }
    assert.match(zh['error.device_required'], /[\u4e00-\u9fff]/)
    assert.match(ta['error.device_required'], /[\u0b80-\u0bff]/)
  })

  it('reach the user through apiErrorText in the UI language, whatever message the backend sent', () => {
    for (const lang of ['en', 'ta', 'zh'] as const) {
      const t = say(lang)
      const noKey = new ApiError(401, 'device_required', 'Send your device key in the X-SIB-Device header.')
      const notInScript = new ApiError(422, 'tts_text_not_in_script', "text is not part of this round's script.")

      assert.equal(apiErrorText(t, noKey), tables[lang]['error.device_required'])
      assert.equal(apiErrorText(t, notInScript), tables[lang]['error.tts_text_not_in_script'])
    }
  })

  it('keep the backend message for a code with no sentence of its own, as before', () => {
    const t = say('en')

    assert.equal(apiErrorText(t, new ApiError(404, 'round_not_found', 'Round not found.')), 'Round not found.')
    assert.equal(apiErrorText(t, new ApiError(0, 'network', 'Could not reach the server.')), en['error.network'])
  })

  it('say nothing about a key in the text the user sees', () => {
    for (const table of Object.values(tables)) {
      for (const key of Object.values(NEW)) assert.doesNotMatch((table as Record<string, string>)[key] ?? '', /[A-Za-z0-9_-]{22,}/)
    }
  })
})
