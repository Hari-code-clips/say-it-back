// The worker's recorded answers while their check upload (endpoint 13) is still owed (2026-10-16). On a weak signal the upload can
// wait minutes, and a reload or a crashed tab would otherwise lose the round. So the job (its clips, mode, sample list and the
// upload's Idempotency-Key) is kept in IndexedDB on this phone from the last answer until the check has an answer, then deleted.
// It is never kept longer than MAX_AGE_MS, and it never leaves the phone except as that upload. Where IndexedDB is missing or
// refuses (a private window, storage full) it is kept in memory only, which survives a dropped signal but not a reload.

export interface PendingUpload {
  briefingId: string
  n: number
  /** The upload's Idempotency-Key: the same on every retry, so the server judges and charges the round once. */
  key: string
  mode: 'live' | 'turn'
  sampleAnswers: string[]
  clips: Record<string, Blob>
  savedAt: number
}

/** The four calls the queue needs from a key-value store. */
export interface UploadStore {
  get(id: string): Promise<PendingUpload | undefined>
  put(id: string, value: PendingUpload): Promise<void>
  delete(id: string): Promise<void>
  all(): Promise<PendingUpload[]>
}

/** A pending upload older than this is deleted unsent: the round has moved on, and the worker's voice is not kept for nothing. */
export const MAX_AGE_MS = 24 * 60 * 60 * 1000

export const uploadId = (briefingId: string, n: number): string => `${briefingId}:${n}`

export function memoryStore(): UploadStore {
  const rows = new Map<string, PendingUpload>()
  return {
    get: async (id) => rows.get(id),
    put: async (id, value) => void rows.set(id, value),
    delete: async (id) => void rows.delete(id),
    all: async () => [...rows.values()],
  }
}

const DB = 'sib-uploads'
const TABLE = 'pending'

const done = <T>(req: IDBRequest<T>): Promise<T> =>
  new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })

/** IndexedDB, one object store keyed by `uploadId`. Blobs are stored as they are (structured clone). */
export function indexedDbStore(factory: IDBFactory): UploadStore {
  let opened: Promise<IDBDatabase> | null = null
  const db = () => {
    opened ??= new Promise<IDBDatabase>((resolve, reject) => {
      const req = factory.open(DB, 1)
      req.onupgradeneeded = () => void req.result.createObjectStore(TABLE)
      req.onsuccess = () => resolve(req.result)
      req.onerror = () => reject(req.error)
      req.onblocked = () => reject(new Error('IndexedDB is blocked'))
    }).catch((e: unknown) => {
      opened = null
      throw e
    })
    return opened
  }
  const table = async (mode: IDBTransactionMode) => (await db()).transaction(TABLE, mode).objectStore(TABLE)
  return {
    get: async (id) => (await done((await table('readonly')).get(id))) as PendingUpload | undefined,
    put: async (id, value) => void (await done((await table('readwrite')).put(value, id))),
    delete: async (id) => void (await done((await table('readwrite')).delete(id))),
    all: async () => (await done((await table('readonly')).getAll())) as PendingUpload[],
  }
}

/** The queue over a primary store (IndexedDB) that falls back to memory for good once the primary fails. Nothing here throws. */
export function createUploadQueue(primary: UploadStore | null, now: () => number = Date.now) {
  const memory = memoryStore()
  let store: UploadStore = primary ?? memory
  const use = async <T>(fn: (s: UploadStore) => Promise<T>, fallback: T): Promise<T> => {
    try {
      return await fn(store)
    } catch {
      if (store === memory) return fallback
      store = memory // a private window or a full disk: the answers stay in memory for this page
      return fn(memory).catch(() => fallback)
    }
  }
  const fresh = (job: PendingUpload | undefined) => job !== undefined && now() - job.savedAt < MAX_AGE_MS
  return {
    /** Keep the job until its check has an answer. */
    save: (job: PendingUpload) => use((s) => s.put(uploadId(job.briefingId, job.n), job), undefined),
    /** The job still owed for this round, if any (an expired one is deleted instead). */
    async load(briefingId: string, n: number): Promise<PendingUpload | undefined> {
      const job = await use((s) => s.get(uploadId(briefingId, n)), undefined)
      if (job && !fresh(job)) await this.drop(briefingId, n)
      return fresh(job) ? job : undefined
    },
    /** The check has an answer (or the round was judged another way): the recordings are deleted from the phone. */
    drop: (briefingId: string, n: number) => use((s) => s.delete(uploadId(briefingId, n)), undefined),
    /** Delete every job of a briefing (its decision is recorded: no answer of it is kept on the phone). */
    async dropBriefing(briefingId: string): Promise<void> {
      for (const job of await use((s) => s.all(), [] as PendingUpload[])) if (job.briefingId === briefingId) await this.drop(job.briefingId, job.n)
    },
    /** Delete every job older than MAX_AGE_MS (run once when the app starts). */
    async sweep(): Promise<void> {
      for (const job of await use((s) => s.all(), [] as PendingUpload[])) if (!fresh(job)) await this.drop(job.briefingId, job.n)
    },
    /** Whether the queue fell back to memory (shown nowhere; for tests and the build note). */
    inMemory: () => store === memory,
  }
}

export type UploadQueue = ReturnType<typeof createUploadQueue>

/** A new Idempotency-Key: 128 random bits as 22 characters of base64url (the server accepts 16 to 64 of A-Z a-z 0-9 _ -). */
export function newUploadKey(fill: (bytes: Uint8Array<ArrayBuffer>) => Uint8Array = (b) => crypto.getRandomValues(b)): string {
  const bytes = fill(new Uint8Array(16))
  let bin = ''
  for (const b of bytes) bin += String.fromCharCode(b)
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** This app's queue: IndexedDB where the browser has it, else memory. */
export const uploads: UploadQueue = createUploadQueue(typeof indexedDB === 'undefined' ? null : indexedDbStore(indexedDB))
