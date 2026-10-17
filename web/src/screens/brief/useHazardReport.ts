import { useEffect, useRef, useState } from 'react'
import { ReportFlow, type ReportSource, type ReportState } from './reportFlow.ts'

// The worker's "Report a problem" (endpoint 21) for React: the rules live in reportFlow.ts. The hook lives above the worker
// screens (BriefRun), so a report being recorded, sent, or failed survives the briefing moving from the stage to the hand-back
// screen, and `holds` keeps the page there until it is sent or deliberately deleted.

export type { ReportSource, ReportState } from './reportFlow.ts'

interface Options {
  openSource: () => Promise<ReportSource>
  send: (audio: Blob | null) => Promise<void>
}

export function useHazardReport({ openSource, send }: Options) {
  const [state, setState] = useState<ReportState>({ kind: 'closed' })
  const [level, setLevel] = useState(0)
  // The latest callbacks, so the flow (made once) never calls a stale closure.
  const deps = useRef({ openSource, send })
  deps.current = { openSource, send }
  const flow = useRef<ReportFlow | null>(null)
  flow.current ??= new ReportFlow({
    openSource: () => deps.current.openSource(),
    send: (audio) => deps.current.send(audio),
    onChange: setState,
  })
  const f = flow.current

  // The level meter while recording (the source's smoothed level, 10 times a second).
  const recording = state.kind === 'recording'
  useEffect(() => {
    if (!recording) return
    const id = setInterval(() => setLevel(f.level), 100)
    return () => {
      clearInterval(id)
      setLevel(0)
    }
  }, [recording, f])

  // Leaving the page (reload, close, typed URL) while a report is held asks the browser to confirm.
  const holds = f.holds
  useEffect(() => {
    if (!holds) return
    const stop = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', stop)
    return () => window.removeEventListener('beforeunload', stop)
  }, [holds])

  useEffect(() => {
    f.revive()
    return () => f.dispose()
  }, [f])

  return {
    state,
    level,
    /** Recording, sending, or failed and not deliberately deleted: the worker screen must not move on. */
    holds,
    open: () => f.open(),
    speak: () => void f.speak(),
    tap: () => void f.tap(),
    finish: () => f.finish(),
    retry: () => void f.retry(),
    cancel: () => f.cancel(),
    confirmDiscard: () => f.confirmDiscard(),
    keep: () => f.keep(),
  }
}

export type HazardReport = ReturnType<typeof useHazardReport>
