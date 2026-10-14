import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { ApiError, createTransport, type Transport } from '../../src/api/transport.ts'

const KEY = 'device-key-'.padEnd(32, 'k')

interface Sent {
  url: string
  init: RequestInit
}

const ok = (body: unknown = {}) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })

function setup(base = 'https://api.example.test/api', answer: (sent: Sent) => Response | Promise<Response> = () => ok()) {
  const sent: Sent[] = []
  const transport = createTransport({
    base,
    deviceKey: () => KEY,
    send: async (url, init) => {
      sent.push({ url, init })
      return answer({ url, init })
    },
  })
  return { transport, sent }
}

const header = (init: RequestInit, name: string) => new Headers(init.headers).get(name)

/** One call of every kind the app makes: a GET, a JSON body with each method, a multipart upload, and blob downloads. */
const KINDS: Array<[string, (t: Transport) => Promise<unknown>]> = [
  ['GET', (t) => t.request('/catalog')],
  ['JSON POST', (t) => t.request('/briefings', { method: 'POST', json: { instruction: 'Switch it off.' } })],
  ['JSON PUT', (t) => t.request('/briefings/b_1/steps', { method: 'PUT', json: { steps: [] } })],
  ['JSON PATCH', (t) => t.request('/briefings/b_1', { method: 'PATCH', json: { instruction: 'x' } })],
  ['multipart upload', (t) => t.request('/briefings/b_1/rounds/1/check', { method: 'POST', form: upload() })],
  ['blob GET', (t) => t.requestBlob('/export/briefings.csv')],
  ['blob POST', (t) => t.requestBlob('/tts', { method: 'POST', json: { briefingId: 'b_1', n: 1, text: 'Hello.' } })],
]

function upload(): FormData {
  const form = new FormData()
  form.append('q1', new Blob(['RIFF....WAVE'], { type: 'audio/wav' }), 'q1.wav')
  form.append('meta', JSON.stringify({ mode: 'turn' }))
  return form
}

describe('the device key on every request', () => {
  for (const [kind, call] of KINDS) {
    it(`goes in the X-SIB-Device header of a ${kind}`, async () => {
      const { transport, sent } = setup()

      await call(transport)

      assert.equal(sent.length, 1)
      assert.equal(header(sent[0]!.init, 'X-SIB-Device'), KEY)
    })

    it(`is not in the URL or the body of a ${kind}`, async () => {
      const { transport, sent } = setup()

      await call(transport)

      assert.ok(!sent[0]!.url.includes(KEY), sent[0]!.url)
      const body = sent[0]!.init.body
      if (typeof body === 'string') assert.ok(!body.includes(KEY))
      if (body instanceof FormData) for (const [name, value] of body.entries()) assert.ok(name !== KEY && value !== KEY)
    })
  }

  it('leaves the multipart content type to the browser, which has to add the boundary', async () => {
    const { transport, sent } = setup()

    await transport.request('/transcribe', { method: 'POST', form: upload() })

    assert.equal(header(sent[0]!.init, 'Content-Type'), null)
  })

  it('sets the JSON content type on a JSON body, beside the key', async () => {
    const { transport, sent } = setup()

    await transport.request('/briefings', { method: 'POST', json: { a: 1 } })

    assert.equal(header(sent[0]!.init, 'Content-Type'), 'application/json')
    assert.equal(header(sent[0]!.init, 'X-SIB-Device'), KEY)
  })

  it('is the key of the moment: a transport asks for it on each request', async () => {
    const sent: string[] = []
    let key = 'first-key-'.padEnd(32, 'a')
    const transport = createTransport({
      base: '/api',
      deviceKey: () => key,
      send: async (_url, init) => {
        sent.push(new Headers(init.headers).get('X-SIB-Device') ?? '')
        return ok()
      },
    })

    await transport.request('/catalog')
    key = 'second-key'.padEnd(32, 'b')
    await transport.request('/catalog')

    assert.deepEqual(sent, ['first-key-'.padEnd(32, 'a'), 'second-key'.padEnd(32, 'b')])
  })
})

describe('where a request goes', () => {
  it('joins an absolute API base and the path', async () => {
    const { transport, sent } = setup('https://say-it-back-api-x.a.run.app/api')

    await transport.request('/briefings?limit=20')

    assert.equal(sent[0]!.url, 'https://say-it-back-api-x.a.run.app/api/briefings?limit=20')
  })

  it('joins the relative default base and the path (local development through the Vite proxy)', async () => {
    const { transport, sent } = setup('/api')

    await transport.requestBlob('/export/briefings.csv')

    assert.equal(sent[0]!.url, '/api/export/briefings.csv')
  })

  it('uses the method asked for, GET by default', async () => {
    const { transport, sent } = setup()

    await transport.request('/health')
    await transport.request('/briefings', { method: 'POST', json: {} })

    assert.deepEqual(sent.map((s) => s.init.method), ['GET', 'POST'])
  })
})

describe('failures', () => {
  it('turns a 401 device_required body into an ApiError with its status and code', async () => {
    const refusal = () => new Response(JSON.stringify({ error: { code: 'device_required', message: 'Send your device key.' } }), { status: 401 })
    const { transport } = setup('/api', refusal)

    await assert.rejects(transport.request('/briefings'), (e: unknown) => e instanceof ApiError && e.status === 401 && e.code === 'device_required' && e.message === 'Send your device key.')
  })

  it("keeps a 404 not_found as one, which is how another browser's briefing looks", async () => {
    const missing = () => new Response(JSON.stringify({ error: { code: 'not_found', message: 'Briefing not found.' } }), { status: 404 })
    const { transport } = setup('/api', missing)

    await assert.rejects(transport.request('/briefings/b_abcdefghijkl'), (e: unknown) => e instanceof ApiError && e.status === 404 && e.code === 'not_found')
  })

  it('gives a response with no JSON body the code http_<status>', async () => {
    const { transport } = setup('/api', () => new Response('<html>Bad Gateway</html>', { status: 502 }))

    await assert.rejects(transport.requestBlob('/tts'), (e: unknown) => e instanceof ApiError && e.status === 502 && e.code === 'http_502')
  })

  it('reports a request that never reaches the server as a network error', async () => {
    const transport = createTransport({
      base: '/api',
      deviceKey: () => KEY,
      send: async () => {
        throw new TypeError('Failed to fetch')
      },
    })

    await assert.rejects(transport.request('/health'), (e: unknown) => e instanceof ApiError && e.code === 'network' && e.status === 0)
  })

  it('reports a request that outlives its timeout as a timeout, and aborts it', async () => {
    let aborted = false
    const transport = createTransport({
      base: '/api',
      deviceKey: () => KEY,
      send: (_url, init) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => {
            aborted = true
            reject(new DOMException('aborted', 'AbortError'))
          })
        }),
    })

    await assert.rejects(transport.request('/health', { timeoutMs: 20 }), (e: unknown) => e instanceof ApiError && e.code === 'timeout')
    assert.ok(aborted)
  })
})
