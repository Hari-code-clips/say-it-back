import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client.ts'

export interface AsyncState<T> {
  data: T | undefined
  error: ApiError | undefined
  loading: boolean
  reload: () => void
}

/** Runs `load` on mount and whenever `deps` change; the latest call wins. */
export function useAsync<T>(load: () => Promise<T>, deps: readonly unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | undefined>(undefined)
  const [error, setError] = useState<ApiError | undefined>(undefined)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  const latest = useRef(0)
  const loadRef = useRef(load)
  loadRef.current = load

  useEffect(() => {
    const call = ++latest.current
    setLoading(true)
    setError(undefined)
    loadRef
      .current()
      .then((value) => {
        if (call === latest.current) setData(value)
      })
      .catch((e: unknown) => {
        if (call === latest.current) setError(e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e)))
      })
      .finally(() => {
        if (call === latest.current) setLoading(false)
      })
  }, [...deps, tick]) // `load` is read through a ref; the caller's deps decide when to re-run

  const reload = useCallback(() => setTick((n) => n + 1), [])
  return { data, error, loading, reload }
}
