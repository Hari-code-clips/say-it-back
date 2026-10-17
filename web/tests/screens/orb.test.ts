import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'

// F2: "Fix the listening orb crowding the 'Speak now' text". The outer ring swells with the voice (index.css `.orb-ring`, up to 1 + K
// times its resting size) and used to rest at the whole box, so it grew into the word under the orb. It now rests inset, so the swell
// tops out at the box's own edge. Read from the two source files, so the numbers cannot drift apart.

const read = (rel: string) => readFileSync(new URL(`../../src/${rel}`, import.meta.url), 'utf8')

const swell = (): number => {
  const css = read('styles/index.css')
  const rule = css.match(/\.orb-ring\s*\{[^}]*scale\(calc\(1 \+ var\(--level, 0\) \* ([0-9.]+)\)\)/)
  assert.ok(rule, 'the .orb-ring swell rule is in index.css')
  return Number(rule[1])
}

const haloInset = (): number => {
  const line = read('screens/brief/Orb.tsx').split('\n').find((l) => l.includes('orb-ring absolute'))
  assert.ok(line, 'the halo element is in Orb.tsx')
  const inset = line.match(/inset-\[(\d+)%\]/)
  assert.ok(inset, `the halo is inset by a percentage: ${line}`)
  return Number(inset[1]) / 100
}

describe('the listening orb stays in its own box', () => {
  it('the halo at its largest (resting size x the swell) is no wider than the orb’s box', () => {
    const resting = 1 - 2 * haloInset()
    const biggest = resting * (1 + swell())
    assert.ok(biggest <= 1.01, `the halo grows to ${(biggest * 100).toFixed(1)}% of the box`)
  })

  it('and still shows: it rests larger than the ring inside it, so the swell is visible', () => {
    const line = read('screens/brief/Orb.tsx').split('\n').find((l) => l.includes('look.ring'))
    const ringInset = Number(line?.match(/inset-\[(\d+)%\]/)?.[1]) / 100
    assert.ok(haloInset() < ringInset, 'the halo is outside the ring')
  })
})
