import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, it } from 'node:test'
import { THEME_COLOR_HEX } from '../../src/theme/scheme.ts'
import { contrast, inSrgb, parseOklch, toHex, toLinearRgb } from '../helpers/oklch.ts'

// The design system's colour rule (web/design.md, v2 of 16 Oct): the site's own safety-sign colours (ISO 7010 / ISO 3864). Paper
// and ink are neutrals; chroma lives in the three verdict families (success = Got it, warning = Ask again, error = Wrong and
// hazard) and in the action blue (primary: buttons, selection, focus; and the worker's ground). Blue is never a verdict. These
// tests read the live tokens out of src/styles/index.css, so the rule cannot drift from the stylesheet.

const root = new URL('../../', import.meta.url)
const read = (path: string) => readFileSync(new URL(path, root), 'utf8')
const css = read('src/styles/index.css')

/** `--color-name: oklch(...)` lines of the @theme block. */
const tokens: Record<string, string> = Object.fromEntries(
  [...css.matchAll(/^\s*--color-([a-z-]+):\s*(oklch\([^)]*\));/gm)].map((m) => [m[1] as string, m[2] as string]),
)
const colour = (name: string) => {
  const value = tokens[name]
  assert.ok(value, `token --color-${name} is missing`)
  return parseOklch(value)
}

const VERDICT_FAMILIES = ['success', 'warning', 'error']
const isVerdict = (name: string) => VERDICT_FAMILIES.some((f) => name === f || name.endsWith(`-${f}`) || name.startsWith(`${f}-`) || name.startsWith(`on-${f}`))
/** The action blue and its tints: what a mandatory-action sign is coloured. `on-primary` is paper, so it stays a neutral. */
const ACTION = ['primary', 'primary-container', 'on-primary-container', 'focus', 'inverse-primary', 'worker-ground']
const isNeutral = (name: string) => !isVerdict(name) && !ACTION.includes(name)
const BLUE = (h: number) => h >= 240 && h <= 265

describe('colour tokens: the site’s safety-sign colours', () => {
  it('declares every token as an OKLCH colour, all inside the sRGB gamut (so the hex fallback is the colour the browser draws)', () => {
    assert.ok(Object.keys(tokens).length >= 40, 'the palette is missing')
    for (const [name, value] of Object.entries(tokens)) assert.ok(inSrgb(toLinearRgb(parseOklch(value))), `--color-${name} ${value} is outside sRGB`)
  })

  it('keeps every neutral under 0.015 chroma: paper, ink, containers, outlines, snackbar, scrim', () => {
    const loud = Object.entries(tokens).filter(([name, v]) => isNeutral(name) && parseOklch(v).c > 0.015)
    assert.deepEqual(loud.map(([name, v]) => `${name} ${v}`), [])
  })

  it('tints every neutral toward the paper hue (at least 0.005 chroma): no flat grey', () => {
    const flat = Object.entries(tokens).filter(([name, v]) => isNeutral(name) && parseOklch(v).c < 0.005)
    assert.deepEqual(flat.map(([name, v]) => `${name} ${v}`), [])
  })

  it('puts chroma only in the three verdict families and the action blue, and gives each its own hue', () => {
    for (const family of VERDICT_FAMILIES) {
      assert.ok(colour(family).c >= 0.1, `${family} should carry chroma`)
      assert.ok(colour(`${family}-container`).c >= 0.025, `${family}-container should carry chroma`)
    }
    const hue = (name: string) => colour(name).h
    assert.ok(Math.abs(hue('success') - 150) <= 15, 'success is green')
    assert.ok(hue('warning') >= 60 && hue('warning') <= 100, 'warning is amber')
    assert.ok(hue('error') >= 15 && hue('error') <= 35, 'error is red')
    for (const name of ACTION) assert.ok(BLUE(hue(name)), `${name} is the action blue (hue ${hue(name).toFixed(0)})`)
    // Blue is never a verdict: at least 90 degrees from green, the nearest verdict hue.
    assert.ok(hue('primary') - hue('success') >= 90, 'the action blue is far from Got it green')
  })

  it('the action blue is the primary: filled buttons, selection and the focus ring are the blue of a mandatory-action sign', () => {
    assert.equal(tokens['focus'], tokens['primary'])
    assert.ok(colour('primary').c >= 0.12, 'a real blue, not a blue-grey')
    assert.ok(colour('primary-container').c >= 0.025 && colour('worker-ground').c >= 0.015, 'its tints carry the hue')
    assert.notEqual(tokens['primary'], tokens['on-surface'], 'buttons are no longer ink')
  })

  it('has one scheme: light', () => {
    assert.ok(!/prefers-color-scheme/.test(css), 'no dark branch')
    assert.match(css, /color-scheme:\s*light;/)
  })
})

describe('contrast (WCAG 2.x ratios)', () => {
  const ratio = (fg: string, bg: string) => contrast(colour(fg), colour(bg))
  const surfaces = ['surface', 'surface-container-lowest', 'surface-container-low', 'surface-container', 'surface-container-high']

  it('ink text on every paper surface is at least 7:1', () => {
    for (const bg of [...surfaces, 'surface-container-highest', 'surface-variant']) assert.ok(ratio('on-surface', bg) >= 7, `on-surface on ${bg}: ${ratio('on-surface', bg).toFixed(2)}`)
  })

  it('secondary text is at least 7:1 on paper and the card face, at least 4.5:1 on the darkest container', () => {
    for (const bg of surfaces) assert.ok(ratio('on-surface-variant', bg) >= 7, `on-surface-variant on ${bg}: ${ratio('on-surface-variant', bg).toFixed(2)}`)
    assert.ok(ratio('on-surface-variant', 'surface-container-highest') >= 4.5)
  })

  it('text on filled and tinted surfaces is at least 7:1 (tints) and 4.5:1 (solid verdict fills)', () => {
    const tinted: [string, string][] = [
      ['on-primary', 'primary'],
      ['on-primary-container', 'primary-container'],
      ['on-secondary-container', 'secondary-container'],
      ['on-success-container', 'success-container'],
      ['on-warning-container', 'warning-container'],
      ['on-error-container', 'error-container'],
      ['inverse-on-surface', 'inverse-surface'],
    ]
    for (const [fg, bg] of tinted) assert.ok(ratio(fg, bg) >= 7, `${fg} on ${bg}: ${ratio(fg, bg).toFixed(2)}`)
    for (const family of VERDICT_FAMILIES) assert.ok(ratio(`on-${family}`, family) >= 4.5, `on-${family} on ${family}: ${ratio(`on-${family}`, family).toFixed(2)}`)
  })

  it('UI boundaries and mark colours are at least 3:1 against every paper surface', () => {
    for (const bg of surfaces) {
      for (const fg of ['outline', 'primary', 'success', 'warning', 'error']) assert.ok(ratio(fg, bg) >= 3, `${fg} on ${bg}: ${ratio(fg, bg).toFixed(2)}`)
    }
  })

  // The ring is drawn 2 px outside its control, so what it touches is what is behind the control: paper, the card face, a
  // tint (a banner) or the worker's ground. A control is never placed on a solid verdict fill.
  it('the focus ring is at least 3:1 (in fact 5:1 or more) against paper, the card face, the worker ground and every tint a control can sit on', () => {
    for (const bg of [...surfaces, 'surface-container-highest', 'primary-container', 'worker-ground', 'success-container', 'warning-container', 'error-container']) {
      assert.ok(ratio('focus', bg) >= 3, `focus on ${bg}: ${ratio('focus', bg).toFixed(2)}`)
    }
  })

  // Worker-held screens sit on the `worker` ground (WorkerShell). Everything a worker reads or presses there must stay as clear
  // as on paper: the words, the Start button, the red problem button, the supervisor's outlined hold.
  it('the worker ground keeps every worker screen as readable as paper, and is visibly not paper', () => {
    assert.ok(ratio('on-surface', 'worker-ground') >= 7, 'the worker’s words')
    assert.ok(ratio('on-surface-variant', 'worker-ground') >= 4.5, 'the quieter line')
    for (const fg of ['primary', 'error', 'outline', 'success']) assert.ok(ratio(fg, 'worker-ground') >= 3, `${fg} on worker-ground: ${ratio(fg, 'worker-ground').toFixed(2)}`)
    assert.ok(colour('worker-ground').c - colour('surface').c >= 0.01, 'a tint you can see, not paper')
  })

  it('a disabled control stays readable: its text is at least 4:1 on its fill', () => {
    assert.ok(ratio('outline', 'surface-container-high') >= 4)
  })

  it('the hairline is a visible line on paper, but only a hairline', () => {
    const r = ratio('outline-variant', 'surface')
    assert.ok(r >= 1.3 && r <= 2, `hairline ${r.toFixed(2)}`)
  })
})

// A colour token named like a type size makes `text-<name>` mean both a colour and a size, and Tailwind then picks the colour:
// on 16 Oct a `--color-worker` turned every `text-worker` line (the worker's big words) into pale 16 px text.
describe('no colour token shares its name with a type size', () => {
  it('so `text-<name>` is never ambiguous', () => {
    const sizes = new Set([...css.matchAll(/^\s*--text-([a-z]+(?:-[a-z]+)*):\s/gm)].map((m) => m[1] as string))
    assert.ok(sizes.has('worker'), 'the worker size token is where this test expects it')
    assert.deepEqual(Object.keys(tokens).filter((name) => sizes.has(name)), [])
  })
})

describe('no colour outside a token', () => {
  const files = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const path = join(dir, name)
      return statSync(path).isDirectory() ? files(path) : /\.(tsx?|css)$/.test(name) ? [path] : []
    })
  const literal = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\boklch\(|\bhwb\(|\blab\(|\blch\(/

  it('has no hex, rgb(), hsl() or oklch() in any source file except the @theme palette in index.css', () => {
    const offenders: string[] = []
    for (const file of files(fileURLToPath(new URL('../../src/', import.meta.url)))) {
      const text = readFileSync(file, 'utf8')
      const lines = text.split('\n')
      lines.forEach((line, i) => {
        if (!literal.test(line)) return
        const isPalette = file.endsWith('styles/index.css') && /^\s*--color-[a-z-]+:\s*oklch\(/.test(line)
        const isComment = /^\s*(\/\/|\/?\*|\*)/.test(line)
        // scheme.ts holds the one literal a <meta> needs; the test below checks it against the token.
        const isThemeColor = file.endsWith('theme/scheme.ts') && line.includes('THEME_COLOR_HEX')
        if (!isPalette && !isComment && !isThemeColor) offenders.push(`${file.split('/src/')[1]}:${i + 1}: ${line.trim()}`)
      })
    }
    assert.deepEqual(offenders, [])
  })
})

describe('theme-color (the one literal a <meta> needs)', () => {
  it('is the sRGB hex of --color-surface, in scheme.ts and in index.html', () => {
    assert.equal(THEME_COLOR_HEX, toHex(colour('surface')))
    assert.match(read('index.html'), new RegExp(`<meta name="theme-color" content="${THEME_COLOR_HEX}"`))
  })
})

describe('design.md', () => {
  const md = read('design.md')
  const rows = [...md.matchAll(/^\| `--color-([a-z-]+)` \| `(oklch\([^)]*\))` \|/gm)]

  it('documents every colour token, with the value index.css uses', () => {
    const documented = Object.fromEntries(rows.map((m) => [m[1] as string, m[2] as string]))
    const wrong = Object.entries(tokens).filter(([name, v]) => documented[name] !== v)
    assert.deepEqual(wrong.map(([name, v]) => `${name}: css ${v}, design.md ${documented[name] ?? 'missing'}`), [])
    assert.deepEqual(Object.keys(documented).filter((n) => !(n in tokens)), [])
  })

  it('names the system: modern-minimal, Workbench and Long Document', () => {
    assert.match(md, /## Genre\s+modern-minimal/)
    assert.match(md, /\*\*Workbench\*\*/)
    assert.match(md, /\*\*Long Document\*\*/)
  })
})

describe('type and motion in the stylesheet', () => {
  it('uses Noto Sans at 400, 600 and 700 only (no 500 in the tokens or in the font request)', () => {
    assert.ok(!/--text-[a-z-]+--font-weight:\s*500\b/.test(css))
    assert.match(read('vite.config.ts'), /const WEIGHTS = ':wght@400;600;700'/)
    assert.match(css, /--font-sans:\s*"Noto Sans"/)
  })

  it('tightens display tracking in Latin only', () => {
    assert.match(css, /html:lang\(en\)\s*\{\s*--tracking-display:\s*-0\.02em;/)
    assert.match(css, /--tracking-display:\s*0em;/)
  })

  it('never transitions the focus ring', () => {
    const rule = /:focus-visible\s*\{([^}]*)\}/.exec(css)?.[1] ?? ''
    assert.ok(rule.includes('outline: 3px solid var(--color-focus)'))
    assert.ok(!/transition|animation/.test(rule))
  })

  it('keeps the hold countdown running under reduced motion (it is the countdown, not decoration)', () => {
    const reduced = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'))
    assert.match(reduced, /\.hold-fill\[data-holding="true"\]\s*\{\s*transition-duration:\s*var\(--hold-ms, 1500ms\)\s*!important/)
    assert.match(reduced, /transition-duration:\s*0\.01ms\s*!important/)
  })

  it('keeps every animation to 200 ms or less (loaders and the listening orb excepted)', () => {
    const animations = [...css.matchAll(/--animate-(rise|fade-in):\s*[a-z-]+\s+(\d+)ms/g)]
    assert.equal(animations.length, 2)
    for (const m of animations) assert.ok(Number(m[2]) <= 200, `${m[1]} ${m[2]}ms`)
  })

  it('has 12 px controls (md and lg are 0.75rem) and no pill in the control radii', () => {
    assert.match(css, /--radius-md:\s*0\.75rem/)
    assert.match(css, /--radius-lg:\s*0\.75rem/)
  })
})
