import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { demoVideoUrl } from '../../src/lib/demoVideo.ts'

describe('demoVideoUrl (VITE_DEMO_VIDEO_URL)', () => {
  it('links nothing when the variable is unset or blank', () => {
    assert.equal(demoVideoUrl(undefined), null)
    assert.equal(demoVideoUrl(''), null)
    assert.equal(demoVideoUrl('   '), null)
  })

  it('links an https URL, as given', () => {
    assert.equal(demoVideoUrl(' https://youtu.be/abc123 '), 'https://youtu.be/abc123')
    assert.equal(demoVideoUrl('https://www.youtube.com/watch?v=abc123'), 'https://www.youtube.com/watch?v=abc123')
  })

  it('links nothing that is not https, or that carries credentials', () => {
    for (const bad of ['http://youtu.be/abc', 'javascript:alert(1)', 'data:text/html,hi', '//youtu.be/abc', 'youtu.be/abc', 'https://user:pw@example.com/v']) {
      assert.equal(demoVideoUrl(bad), null, bad)
    }
  })
})
