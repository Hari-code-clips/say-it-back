import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'

// Record bug (note 29): the "What was checked" row was chip | step text | tag on one line, so at 375 px the text got a word per line.
// The row is now one component: chip and tag on a line above the text, at every width. This suite cannot lay the page
// out (node:test, no DOM), so it pins the structure; the width check itself runs in the browser (note 29, "Record row squeeze").

const source = (path: string) => readFileSync(new URL(`../../src/screens/${path}`, import.meta.url), 'utf8')

describe('the verdict row (StepRow)', () => {
  const row = source('result/StepRow.tsx')

  it('is stacked at every width: chip and tag on a line of their own, then the text at full width', () => {
    assert.match(row, /<div className="flex flex-wrap items-center gap-2">/)
    assert.ok(!/\b(sm|md|lg|xl):(grid|flex|contents)\b|grid-cols/.test(row), 'no side-by-side layout at any width')
  })

  it('the text is never a flex-1 item squeezed between the chip and the tag', () => {
    assert.ok(!/flex-1/.test(row))
  })

  it('every list of steps with a verdict uses it', () => {
    for (const file of ['RecordScreen.tsx', 'DecisionScreen.tsx', 'ReexplainScreen.tsx', 'result/ResultScreen.tsx']) {
      assert.match(source(file), /<StepRow\b/, file)
      assert.ok(!/script-text min-w-0 flex-1 text-body-lg/.test(source(file)), `${file}: no chip | text | tag line`)
    }
  })

  it('the Record screen passes "Open at decision" as the row\'s tag, not as a third column of its own', () => {
    assert.match(source('RecordScreen.tsx'), /tag=\{decision\?\.openStepIds\.includes\(s\.id\) \?/)
  })

  it('the Records list keeps its text column too: the status chip sits under the text until 840 px', () => {
    const records = source('RecordsScreen.tsx')
    assert.match(records, /<span className="block pt-1 md:hidden">\{status\}<\/span>/)
    assert.match(records, /<span className="hidden md:inline-flex">\{status\}<\/span>/)
    assert.ok(!/sm:inline-flex|sm:hidden/.test(records))
  })
})
