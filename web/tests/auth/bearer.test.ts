import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { ApiError, createTransport, type Transport } from '../../src/api/transport.ts'

// Pilot accounts (build-notes/34): a firebase build's transport sends the Firebase ID token on every request, of every kind,
// asks for a fresh one once when the server answers 401 `bad_token`, and the default transport (no `authToken`) sends none.

const KEY = 'device-key-'.padEnd(32, 'k')
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const refused = (code: string) => json(401, { error: { code, message: 'no' } })
const auth = (init: RequestInit) => new Headers(init.headers).get('Authorization')

function setup(answers: Array<() => Response>, authToken?: (force: boolean) => Promise<string | null>) {
  const sent: RequestInit[] = []
  const forced: boolean[] = []
  const transport = createTransport({
    base: '/api',
    deviceKey: () => KEY,
    send: async (_url, init) => {
      sent.push(init)
      return (answers.shift() ?? (() => json(200, {})))()
    },
    authToken: authToken
      ? async (force) => {
          forced.push(force)
          return authToken(force)
        }
      : undefined,
  })
  return { transport, sent, forced }
}

const KINDS: Array<[string, (t: Transport) => Promise<unknown>]> = [
  ['GET', (t) => t.request('/me')],
  ['PUT json', (t) => t.request('/orgs/acme/members/x', { method: 'PUT', json: { roles: {} } })],
  ['multipart', (t) => t.request('/transcribe', { method: 'POST', form: new FormData() })],
  ['blob', (t) => t.requestBlob('/export/briefings.csv')],
]

describe('the ID token on every request (firebase builds)', () => {
  for (const [kind, call] of KINDS) {
    it(`sends Authorization: Bearer on a ${kind} request, beside the device key`, async () => {
      const { transport, sent } = setup([], async () => 'tok.en.one')
      await call(transport)
      assert.equal(auth(sent[0]), 'Bearer tok.en.one')
      assert.equal(new Headers(sent[0].headers).get('X-SIB-Device'), KEY)
    })
  }

  it('the default transport sends no Authorization header', async () => {
    const { transport, sent } = setup([])
    for (const [, call] of KINDS) await call(transport)
    assert.ok(sent.every((init) => auth(init) === null))
  })

  it('a signed-out user (no token) sends no header', async () => {
    const { transport, sent } = setup([], async () => null)
    await transport.request('/me')
    assert.equal(auth(sent[0]), null)
  })

  it('a 401 bad_token gets one fresh token and one more try', async () => {
    const { transport, sent, forced } = setup([() => refused('bad_token')], async (force) => (force ? 'fresh.to.ken' : 'stale.to.ken'))
    assert.deepEqual(await transport.request('/me'), {})
    assert.deepEqual(forced, [false, true])
    assert.deepEqual(sent.map(auth), ['Bearer stale.to.ken', 'Bearer fresh.to.ken'])
  })

  it('a second refusal is reported, never retried again', async () => {
    const errors: ApiError[] = []
    const transport = createTransport({
      base: '/api',
      deviceKey: () => KEY,
      send: async () => refused('bad_token'),
      authToken: async () => 'a.b.c',
      onError: (e) => errors.push(e),
    })
    await assert.rejects(transport.request('/me'), (e: ApiError) => e.code === 'bad_token')
    assert.equal(errors.length, 1)
  })

  it('other refusals are not retried', async () => {
    for (const code of ['auth_required', 'forbidden', 'domain_not_allowed']) {
      const { transport, sent } = setup([() => (code === 'auth_required' ? refused(code) : json(403, { error: { code } }))], async () => 'a.b.c')
      await assert.rejects(transport.request('/me'), (e: ApiError) => e.code === code)
      assert.equal(sent.length, 1, code)
    }
  })

  it('without authToken a 401 bad_token is not retried (the default build is unchanged)', async () => {
    const { transport, sent } = setup([() => refused('bad_token')])
    await assert.rejects(transport.request('/me'))
    assert.equal(sent.length, 1)
  })
})
