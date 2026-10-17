import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { createHold, HOLD_MS, type HoldPhase } from '../../src/ui/holdToConfirm.ts'
import { FakeClock } from '../helpers/fakeClock.ts'

// The supervisor's exit on a worker screen: press and hold 1.5 s. A tap, a short press or a moved finger must never confirm.

function rig(durationMs?: number) {
  const clock = new FakeClock()
  const log: string[] = []
  const phases: HoldPhase[] = []
  const hold = createHold(
    clock,
    { onConfirm: () => log.push('confirm'), onShortPress: () => log.push('short'), onPhase: (p) => phases.push(p) },
    durationMs,
  )
  return { clock, log, phases, hold }
}

describe('press and hold', () => {
  it('is 1.5 seconds', () => {
    assert.equal(HOLD_MS, 1500)
  })

  it('confirms at 1.5 s and not a millisecond before', () => {
    const { clock, log, hold } = rig()
    hold.press('pointer')
    clock.advanceTo(1.499)
    assert.deepEqual(log, [])
    assert.equal(hold.phase, 'holding')
    clock.advanceTo(1.5)
    assert.deepEqual(log, ['confirm'])
    assert.equal(hold.phase, 'confirmed')
  })

  it('a release before the time is a short press: no confirm, no timer left behind', () => {
    const { clock, log, hold } = rig()
    hold.press('pointer')
    clock.advanceTo(0.8)
    hold.release('pointer')
    assert.deepEqual(log, ['short'])
    assert.equal(hold.phase, 'idle')
    assert.equal(clock.waiting, 0)
    clock.advanceTo(5)
    assert.deepEqual(log, ['short'])
  })

  it('confirms once per hold; releasing after the confirm says nothing; the next hold works', () => {
    const { clock, log, hold } = rig()
    hold.press('key')
    clock.advanceTo(10)
    hold.release('key')
    assert.deepEqual(log, ['confirm'])
    assert.equal(hold.phase, 'idle')
    hold.press('key')
    clock.advanceTo(12)
    assert.deepEqual(log, ['confirm', 'confirm'])
  })

  it('ignores key auto-repeat and a second finger: they cannot restart or shorten the hold', () => {
    const { clock, log, hold } = rig()
    hold.press('key')
    clock.advanceTo(1)
    hold.press('key') // auto-repeat
    hold.press('pointer') // another input
    clock.advanceTo(1.4)
    assert.deepEqual(log, [])
    clock.advanceTo(1.5)
    assert.deepEqual(log, ['confirm'])
  })

  it('only the input that is holding can release it', () => {
    const { clock, log, hold } = rig()
    hold.press('pointer')
    hold.release('key')
    assert.equal(hold.phase, 'holding')
    clock.advanceTo(1.5)
    assert.deepEqual(log, ['confirm'])
  })

  it('an interrupted press (finger slid off, focus lost, touch cancelled) is silent: no confirm, no short-press hint', () => {
    const { clock, log, hold, phases } = rig()
    hold.press('pointer')
    clock.advanceTo(1.2)
    hold.abort()
    assert.deepEqual(log, [])
    assert.deepEqual(phases, ['holding', 'idle'])
    assert.equal(clock.waiting, 0)
    clock.advanceTo(5)
    assert.deepEqual(log, [])
  })

  it('reports each phase, so the fill can follow it', () => {
    const { clock, phases, hold } = rig()
    hold.press('pointer')
    clock.advanceTo(1.5)
    hold.release('pointer')
    assert.deepEqual(phases, ['holding', 'confirmed', 'idle'])
  })

  it('takes its duration from the caller', () => {
    const { clock, log, hold } = rig(3000)
    hold.press('pointer')
    clock.advanceTo(2.9)
    assert.deepEqual(log, [])
    clock.advanceTo(3)
    assert.deepEqual(log, ['confirm'])
  })
})
