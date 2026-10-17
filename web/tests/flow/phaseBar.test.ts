import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import { contextLine, contextParts, languagePair } from '../../src/flow/contextLine.ts'
import { BAR_PHASE, PHASE_BAR, phaseBar, type FlowStep } from '../../src/flow/phases.ts'

// The flow header names the phase (Steps, Script, Worker, Result, Decision) instead of counting "Step N of 7".
// Rounds are the only count, and they live in the context line.

describe('named phases', () => {
  it('are Steps, Script, Worker, Result, Decision, in that order, in every UI language', () => {
    assert.deepEqual(PHASE_BAR, ['steps', 'script', 'worker', 'result', 'decision'])
    assert.deepEqual(PHASE_BAR.map((p) => en[`phasebar.${p}`]), ['Steps', 'Script', 'Worker', 'Result', 'Decision'])
    for (const table of [ta, zh]) for (const p of PHASE_BAR) assert.match(table[`phasebar.${p}`], /\S/)
  })

  it('there is no "Step N of M" counter any more', () => {
    for (const table of [en, ta, zh]) assert.ok(!('flow.step' in table))
  })

  it('every screen of the flow has a phase, except Start (it runs before a briefing exists)', () => {
    const steps: FlowStep[] = ['start', 'instruction', 'steps', 'script', 'brief', 'result', 'reexplain', 'decision', 'record']
    assert.deepEqual(steps.filter((s) => BAR_PHASE[s] === null), ['start'])
    assert.deepEqual(phaseBar('start'), [])
  })

  it('mark where the screen is among the five', () => {
    assert.deepEqual(phaseBar('brief').map((p) => p.state), ['done', 'done', 'current', 'todo', 'todo'])
    assert.deepEqual(phaseBar('steps').map((p) => p.state), ['current', 'todo', 'todo', 'todo', 'todo'])
    assert.deepEqual(phaseBar('record').map((p) => p.state), ['done', 'done', 'done', 'done', 'current'])
  })

  it('put Re-explain under Result and Instruction under Steps, so a second round never makes the bar jump', () => {
    assert.equal(BAR_PHASE.reexplain, 'result')
    assert.equal(BAR_PHASE.instruction, 'steps')
  })
})

describe('the one context line', () => {
  it('reads task, language pair, round', () => {
    assert.equal(contextLine(['Crane lift', languagePair('English', 'தமிழ்'), 'Round 1 of 3']), 'Crane lift · English → தமிழ் · Round 1 of 3')
  })

  it('leaves no stray separator for a part that is missing', () => {
    assert.equal(contextLine(['Crane lift', false, null, undefined, '  ', 'Round 2 of 3']), 'Crane lift · Round 2 of 3')
    assert.equal(contextLine([]), '')
  })

  it('gives the parts separately, so the screen can keep each on one line', () => {
    assert.deepEqual(contextParts(['Crane lift', false, 'English → தமிழ்', ' Round 1 of 3 ']), ['Crane lift', 'English → தமிழ்', 'Round 1 of 3'])
  })

  it('carries a permit between the languages and the round', () => {
    assert.equal(contextLine(['Crane lift', 'English → தமிழ்', 'PTW-123 · worker 1 of 2', 'Round 1 of 3']), 'Crane lift · English → தமிழ் · PTW-123 · worker 1 of 2 · Round 1 of 3')
  })
})
