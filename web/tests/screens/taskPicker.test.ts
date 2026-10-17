import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { en } from '../../src/i18n/en.ts'
import { ta } from '../../src/i18n/ta.ts'
import { zh } from '../../src/i18n/zh.ts'
import { nextOpen } from '../../src/screens/start/taskPickerState.ts'

// Follow-up to F8 (note 29): the task list is collapsed to the chosen task, so the permit block is on the first screen of a phone.
// Every task stays reachable: one press on the row opens the list, a tap, Space or Enter picks and closes it, arrows only move.

const source = (path: string) => readFileSync(new URL(`../../src/screens/${path}`, import.meta.url), 'utf8')

describe('when the task list is open', () => {
  it('"Change task" opens it, and again closes it', () => {
    assert.equal(nextOpen(false, 'toggle'), true)
    assert.equal(nextOpen(true, 'toggle'), false)
  })

  it('picking a task closes it, whichever way it was picked (tap, click, Space, Enter)', () => {
    assert.equal(nextOpen(true, 'pick'), false)
  })

  it('an arrow key moves the selection and leaves the list open (the keyboard user is still choosing)', () => {
    assert.equal(nextOpen(true, 'arrow'), true)
    assert.equal(nextOpen(false, 'arrow'), false)
  })

  it('Escape closes it', () => {
    assert.equal(nextOpen(true, 'escape'), false)
  })
})

describe('the task picker', () => {
  const picker = source('start/TaskPicker.tsx')

  it('starts closed, and the closed state is one row with "Change task"', () => {
    assert.match(picker, /useState\(false\)/)
    assert.match(picker, /t\('start\.changeTask'\)/)
    assert.equal(en['start.changeTask'], 'Change task')
    for (const table of [ta, zh]) assert.match(table['start.changeTask'], /\S/)
  })

  it('is a disclosure a keyboard and a screen reader can drive: aria-expanded, aria-controls, native radios, arrows kept apart from picks', () => {
    assert.match(picker, /aria-expanded=\{open\}/)
    assert.match(picker, /aria-controls=\{listId\}/)
    assert.match(picker, /type="radio"/)
    assert.match(picker, /startsWith\('Arrow'\)/)
    assert.match(picker, /arrowing\.current \? 'arrow' : 'pick'/)
    assert.match(picker, /e\.key === 'Escape'/)
    assert.match(picker, /e\.key === 'Enter' \|\| e\.key === ' '/)
  })

  it('every task is in the list when it opens (the list is the screen\'s options, not a subset)', () => {
    // 17 Oct: grouped under their domain headings (groupByHeading keeps every option: tests/domains/domains.test.ts).
    assert.match(picker, /groupByHeading\(options\)\.map\(/)
    assert.match(picker, /g\.items\.map\(\(o\) =>/)
  })

  it('the Start screen still puts the permit block right after the task section', () => {
    const screen = source('StartScreen.tsx')
    assert.ok(screen.indexOf('<TaskPicker') < screen.indexOf('<PermitBlock'))
    assert.ok(screen.indexOf('<PermitBlock') < screen.indexOf('id="start-site"'))
  })
})
