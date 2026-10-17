import { useEffect, useState } from 'react'

/**
 * Whole seconds since the calling component mounted, updated once a second. Each tick reads the clock rather than counting
 * ticks, so a tab the browser throttled in the background shows the true time when it comes back.
 */
export function useElapsedSeconds(): number {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const start = Date.now()
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000)
    return () => clearInterval(id)
  }, [])
  return elapsed
}
