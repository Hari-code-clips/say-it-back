import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { privacy as en } from '../../src/i18n/en/privacy.ts'
import { privacy as ta } from '../../src/i18n/ta/privacy.ts'
import { privacy as zh } from '../../src/i18n/zh/privacy.ts'

// Security fixes B, I2 (build-notes/36-security-fixes-b.md): the app writes no device key or internet address into its own logs,
// but Google's platform request logs (Cloud Run) do record a client address. The privacy page says "the app's own logs", so a
// careful reader does not take it as "no address anywhere".

describe('the privacy page on logs', () => {
  it('claims only the app’s own logs, in every UI language', () => {
    assert.match(en['privacy.collect.device'], /no key or internet address appears in the app's own logs\.$/)
    assert.doesNotMatch(en['privacy.collect.device'], /appears in a log\b/)
    assert.ok(ta['privacy.collect.device'].includes('செயலியின் சொந்தப் பதிவுக் குறிப்புகளில்'))
    assert.ok(zh['privacy.collect.device'].includes('本应用自己的日志里'))
  })

  it('marks the Tamil and Chinese lines as drafts, the way those files do', () => {
    for (const lang of ['ta', 'zh']) {
      const line = readFileSync(new URL(`../../src/i18n/${lang}/privacy.ts`, import.meta.url), 'utf8')
        .split('\n')
        .find((l) => l.includes("'privacy.collect.device'"))
      assert.match(line ?? '', /DRAFT, NEEDS NATIVE-SPEAKER REVIEW/, lang)
    }
  })
})
