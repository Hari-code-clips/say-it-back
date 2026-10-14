import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { DEVICE_HEADER, deviceKey, isDeviceKey, loadDeviceKey, newDeviceKey, type FillRandom, type KeyStorage } from '../../src/api/deviceKey.ts'

/** The contract's rule for a key (docs/API.md, "Callers and ownership"), written out again so a change to the code cannot move it. */
const CONTRACT = /^[A-Za-z0-9_-]{22,64}$/

function memoryStorage(initial?: string): KeyStorage & { writes: number; value: string | null } {
  const s = {
    writes: 0,
    value: initial ?? null,
    getItem: () => s.value,
    setItem: (_name: string, value: string) => {
      s.writes++
      s.value = value
    },
  }
  return s
}

const brokenStorage = (): KeyStorage => ({
  getItem: () => {
    throw new DOMException('The operation is insecure.', 'SecurityError')
  },
  setItem: () => {
    throw new DOMException('The quota has been exceeded.', 'QuotaExceededError')
  },
})

describe('the device header', () => {
  it('is X-SIB-Device, the name the backend reads', () => {
    assert.equal(DEVICE_HEADER, 'X-SIB-Device')
  })
})

describe('newDeviceKey', () => {
  it('is 22 to 64 characters of the base64url alphabet, as the contract says', () => {
    const key = newDeviceKey()

    assert.match(key, CONTRACT)
    assert.ok(isDeviceKey(key))
  })

  it('is made from at least 16 random bytes (128 bits), asked of the random source once', () => {
    const asked: number[] = []

    newDeviceKey((bytes) => {
      asked.push(bytes.length)
      bytes.fill(1)
    })

    assert.equal(asked.length, 1)
    assert.ok(asked[0]! >= 16, `${asked[0]} bytes`)
  })

  it('writes bytes that base64 would show as "+", "/" and "=" in the URL-safe alphabet, with no padding', () => {
    const fill: FillRandom = (bytes) => {
      for (let i = 0; i < bytes.length; i++) bytes[i] = [0xfb, 0xff, 0xbf][i % 3]!
    }

    const key = newDeviceKey(fill)

    assert.match(key, CONTRACT)
    assert.ok(key.includes('-') && key.includes('_'), key)
    assert.doesNotMatch(key, /[+/=]/)
  })

  it('differs from one call to the next', () => {
    const keys = new Set(Array.from({ length: 50 }, () => newDeviceKey()))

    assert.equal(keys.size, 50)
  })
})

describe('isDeviceKey', () => {
  it('accepts exactly what the backend accepts', () => {
    assert.ok(isDeviceKey('a'.repeat(22)))
    assert.ok(isDeviceKey('A1_-'.repeat(16)))
    assert.ok(!isDeviceKey('a'.repeat(21)))
    assert.ok(!isDeviceKey('a'.repeat(65)))
    assert.ok(!isDeviceKey(`${'a'.repeat(22)}=`))
    assert.ok(!isDeviceKey(`${'a'.repeat(21)} `))
    assert.ok(!isDeviceKey(`${'a'.repeat(21)}\n`))
    assert.ok(!isDeviceKey(null) && !isDeviceKey(undefined) && !isDeviceKey(42))
  })
})

describe('loadDeviceKey', () => {
  it('makes a key once, stores it, and returns the stored one afterwards', () => {
    const storage = memoryStorage()

    const first = loadDeviceKey(storage)
    const second = loadDeviceKey(storage)

    assert.match(first, CONTRACT)
    assert.equal(second, first)
    assert.equal(storage.value, first)
    assert.equal(storage.writes, 1)
  })

  it('returns a key that is already stored without writing', () => {
    const stored = 'stored-key-'.padEnd(32, 'x')
    const storage = memoryStorage(stored)

    assert.equal(loadDeviceKey(storage), stored)
    assert.equal(storage.writes, 0)
  })

  it('replaces a stored value that is not a key', () => {
    const storage = memoryStorage('not a key!')

    const key = loadDeviceKey(storage)

    assert.match(key, CONTRACT)
    assert.equal(storage.value, key)
  })

  it('falls back to a key in memory when storage can be neither read nor written (private mode, blocked site data)', () => {
    const key = loadDeviceKey(brokenStorage())

    assert.match(key, CONTRACT)
  })

  it('falls back to a key in memory when there is no storage at all', () => {
    assert.match(loadDeviceKey(undefined), CONTRACT)
  })

  it('uses a key that a second tab wrote between our write and our read, so both tabs agree', () => {
    const theirs = 'their-key-'.padEnd(32, 'y')
    let reads = 0
    const racing: KeyStorage = { getItem: () => (reads++ === 0 ? null : theirs), setItem: () => undefined }

    assert.equal(loadDeviceKey(racing), theirs)
  })

  it('uses the key it made when storage accepts the write but hands back nothing', () => {
    const forgetful: KeyStorage = { getItem: () => null, setItem: () => undefined }

    assert.match(loadDeviceKey(forgetful), CONTRACT)
  })
})

describe('deviceKey', () => {
  it('is one stable key for the whole page when site data is blocked, so every request of the session has the same owner', () => {
    const original = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      get() {
        throw new DOMException('The operation is insecure.', 'SecurityError') // what a browser does with site data blocked
      },
    })
    try {
      const first = deviceKey()
      const second = deviceKey()

      assert.match(first, CONTRACT)
      assert.equal(second, first)
    } finally {
      if (original) Object.defineProperty(globalThis, 'localStorage', original)
      else Reflect.deleteProperty(globalThis, 'localStorage')
    }
  })
})
