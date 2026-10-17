import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { availability, buttonClass, SIZE, VARIANT, type ButtonVariant } from '../../src/ui/buttonLook.ts'

// web/design.md, "CTA voice" and "Components and states": 12 px rectangles (never pills), 48 px targets, a 64 px primary, and a
// disabled button that says why. The class tables are plain data, so they are checked here without a browser.

const VARIANTS = Object.keys(VARIANT) as ButtonVariant[]

describe('shape and size', () => {
  it('is a 12 px rectangle in every variant and size: never a pill', () => {
    for (const variant of VARIANTS) {
      for (const size of ['md', 'lg', 'xl'] as const) {
        const cls = buttonClass({ variant, size }, false)
        assert.match(cls, /\brounded-md\b/, `${variant}/${size}`)
        assert.ok(!/rounded-(full|xl|2xl|3xl)/.test(cls), `${variant}/${size} is a pill: ${cls}`)
      }
    }
  })

  it('is at least 48 px tall at the smallest size, 64 px for the primary and 76 px for the worker button', () => {
    assert.match(SIZE.md, /\bmin-h-12\b/)
    assert.match(SIZE.lg, /\bmin-h-16\b/)
    assert.match(SIZE.xl, /min-h-\[4\.75rem\]/)
  })

  it('has a state layer (hover, press) and a 1 px press on every variant', () => {
    for (const variant of VARIANTS) {
      const cls = buttonClass({ variant }, false)
      assert.match(cls, /\bstate-layer\b/)
      assert.match(cls, /active:translate-y-px/)
    }
  })

  it('draws the primary as ink on paper and the secondary as an outline, with no tonal fill left', () => {
    assert.match(VARIANT.filled, /\bbg-primary\b.*\btext-on-primary\b/)
    assert.match(VARIANT.outlined, /border-\[1\.5px\] border-outline/)
    assert.equal(VARIANT.tonal, VARIANT.outlined)
    assert.ok(!VARIANTS.some((v) => /secondary-container|primary-container/.test(VARIANT[v])))
  })

  it('makes the hazard button the only red one, and the only red fill', () => {
    assert.match(VARIANT.error, /\bbg-error\b/)
    for (const v of VARIANTS.filter((v) => v !== 'error')) assert.ok(!/\bbg-error\b/.test(VARIANT[v]), v)
  })
})

describe('error and success states swap the colours, they do not stack with the variant\'s own', () => {
  it('a filled button in error is red, not ink and red at once', () => {
    const cls = buttonClass({ variant: 'filled', status: 'error' }, true)
    assert.match(cls, /\bbg-error\b/)
    assert.ok(!/\bbg-primary\b/.test(cls))
  })

  it('an outlined button in success is green, with no ink border left', () => {
    const cls = buttonClass({ variant: 'outlined', status: 'success' }, true)
    assert.match(cls, /\bborder-success\b/)
    assert.ok(!/(?<![:\w-])border-outline(?![\w-])/.test(cls))
  })
})

describe('a disabled button says why (availability)', () => {
  it('with a reason, it stays focusable: aria-disabled, not disabled, and the reason is shown', () => {
    const a = availability({ disabled: true, disabledReason: 'Choose Go or No-go first' })
    assert.deepEqual(a, { nativeDisabled: false, ariaDisabled: true, reason: 'Choose Go or No-go first' })
  })

  it('without a reason, it is natively disabled and shows nothing', () => {
    assert.deepEqual(availability({ disabled: true }), { nativeDisabled: true, ariaDisabled: false, reason: undefined })
    assert.deepEqual(availability({ disabled: true, disabledReason: '   ' }), { nativeDisabled: true, ariaDisabled: false, reason: undefined })
  })

  it('an enabled button shows no reason, even if one is passed', () => {
    assert.deepEqual(availability({ disabled: false, disabledReason: 'Not needed' }), { nativeDisabled: false, ariaDisabled: false, reason: undefined })
    assert.deepEqual(availability({ disabledReason: 'Not needed' }), { nativeDisabled: false, ariaDisabled: false, reason: undefined })
  })

  it('while busy it is natively disabled and shows no reason: it is working, not blocked', () => {
    assert.deepEqual(availability({ busy: true }), { nativeDisabled: true, ariaDisabled: false, reason: undefined })
    assert.deepEqual(availability({ busy: true, disabled: true, disabledReason: 'Wait' }), { nativeDisabled: true, ariaDisabled: false, reason: undefined })
  })
})
