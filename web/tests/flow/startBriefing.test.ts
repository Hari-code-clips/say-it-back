import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { saveStartBriefing } from '../../src/flow/startBriefing.ts'

/** Stands in for POST /api/briefings and PATCH /api/briefings/{id}. */
function fakeApi() {
  const calls: string[] = []
  return {
    calls,
    io: {
      create: async () => {
        calls.push('create')
        return { id: 'b_abcdefghijkl' }
      },
      patch: async (id: string, instruction: string) => {
        calls.push(`patch ${id} ${instruction}`)
      },
    },
  }
}

describe('saveStartBriefing', () => {
  it('creates the briefing on the first attempt', async () => {
    const api = fakeApi()
    const id = await saveStartBriefing({ id: null }, 'Isolate the breaker.', api.io)
    assert.equal(id, 'b_abcdefghijkl')
    assert.deepEqual(api.calls, ['create'])
  })

  it('patches the same briefing on a retry instead of creating a second one, even from an older closure', async () => {
    // A failed extract leaves an error message whose Retry action keeps the `submit` of the render it was made in.
    // That old closure and the new one must see the same briefing: Retry used to create a second, empty record.
    const api = fakeApi()
    const held = { id: null as string | null }
    const submitFromFirstRender = (text: string) => saveStartBriefing(held, text, api.io)
    await submitFromFirstRender('Isolate the breaker.') // creates; the extract that follows fails
    const submitFromLaterRender = (text: string) => saveStartBriefing(held, text, api.io)
    await submitFromFirstRender('Isolate the breaker.') // Retry from the error message
    await submitFromLaterRender('Isolate and lock the breaker.') // or the button again, with an edited text
    assert.deepEqual(api.calls, ['create', 'patch b_abcdefghijkl Isolate the breaker.', 'patch b_abcdefghijkl Isolate and lock the breaker.'])
  })

  it('creates again when the first create failed, so no id is remembered for a briefing that does not exist', async () => {
    const held = { id: null as string | null }
    await assert.rejects(
      saveStartBriefing(held, 'x', {
        create: async () => {
          throw new Error('offline')
        },
        patch: async () => undefined,
      }),
      /offline/,
    )
    assert.equal(held.id, null)
    const api = fakeApi()
    await saveStartBriefing(held, 'x', api.io)
    assert.deepEqual(api.calls, ['create'])
  })
})
