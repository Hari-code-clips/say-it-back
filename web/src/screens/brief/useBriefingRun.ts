import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, wsLocation } from '../../api/client.ts'
import { api } from '../../api/endpoints.ts'
import type { Briefing, Round } from '../../api/types.ts'
import { clipKey, saveClips } from '../../audio/clips.ts'
import { Mic } from '../../audio/mic.ts'
import { Player } from '../../audio/player.ts'
import { LiveSession } from '../../live/liveSession.ts'
import { SessionError, type BriefingSession, type StageEvents, type StagePhase } from '../../live/session.ts'
import { getSocketFactory } from '../../live/socket.ts'
import { TurnSession } from '../../live/turnSession.ts'

export type RunMode = 'live' | 'turn'

export type RunState =
  | { kind: 'ready' }
  | { kind: 'running'; mode: RunMode; phase: StagePhase }
  | { kind: 'failed'; mode: RunMode; error: unknown }
  | { kind: 'submitting' }
  | { kind: 'submit_failed'; error: unknown }

interface Options {
  briefing: Briefing
  round: Round
  /** The round was judged (check succeeded, or the server had already finished it). */
  onJudged: () => Promise<void>
  refresh: () => Promise<Briefing>
}

/**
 * Runs one briefing round: opens the player and mic from the tap that started it, runs the Live or
 * Turn session, then POSTs the per-question WAVs to /check. If Live fails, the same round can be
 * run again in Turn mode.
 */
export function useBriefingRun({ briefing, round, onJudged, refresh }: Options) {
  const [state, setState] = useState<RunState>({ kind: 'ready' })
  const [captions, setCaptions] = useState({ model: '', worker: '' })
  const [heard, setHeard] = useState(false)
  const session = useRef<BriefingSession | null>(null)
  const mic = useRef<Mic | null>(null)
  const player = useRef<Player | null>(null)
  const phase = useRef<StagePhase>({ kind: 'connecting' })
  const pending = useRef<{ clips: Record<string, Blob>; mode: RunMode } | null>(null)
  const modeRef = useRef<RunMode>('live')
  // "End round" can be tapped while the mic is still opening or the ticket is being fetched, before
  // a session exists to abort. The flag is checked between the start-up steps.
  const aborted = useRef(false)
  const guard = () => {
    if (aborted.current) throw new SessionError('aborted', 'The briefing was ended.')
  }

  const release = useCallback(async () => {
    session.current = null
    const m = mic.current
    const p = player.current
    mic.current = null
    player.current = null
    await Promise.all([m?.close(), p?.close()])
  }, [])

  const events: StageEvents = {
    onPhase: (next) => {
      phase.current = next
      setState({ kind: 'running', mode: modeRef.current, phase: next })
      if (next.kind === 'speaking') setCaptions((c) => ({ ...c, model: '' }))
      if (next.kind === 'listening') {
        setCaptions((c) => ({ ...c, worker: '' }))
        setHeard(false)
      }
    },
    onCaption: (role, text) => setCaptions((c) => ({ ...c, [role]: text })),
    onSpeech: setHeard,
  }

  const submit = useCallback(async () => {
    const job = pending.current
    if (!job) return
    setState({ kind: 'submitting' })
    saveClips(clipKey(briefing.id, round.n), job.clips)
    try {
      await api.check(briefing.id, round.n, job.clips, job.mode)
    } catch (e) {
      // The server may have finished after the client gave up (a timeout, a dropped connection): look before retrying.
      const judgedAlready = e instanceof ApiError && e.code === 'invalid_state'
      const fresh = judgedAlready ? undefined : await refresh().catch(() => undefined)
      if (judgedAlready || (fresh && fresh.status !== 'briefing')) return onJudged()
      setState({ kind: 'submit_failed', error: e })
      return
    }
    await onJudged()
  }, [briefing.id, round.n, onJudged, refresh])

  const start = useCallback(
    async (mode: RunMode) => {
      modeRef.current = mode
      aborted.current = false
      phase.current = { kind: 'connecting' }
      setCaptions({ model: '', worker: '' })
      setState({ kind: 'running', mode, phase: phase.current })
      const p = new Player()
      player.current = p
      try {
        await p.start() // both audio contexts are created inside the tap
        guard()
        const m = await Mic.open()
        mic.current = m
        guard()
        const { script } = round
        let s: BriefingSession
        if (mode === 'live') {
          const ticket = await api.liveSession(briefing.id, round.n)
          guard()
          s = new LiveSession({
            wsUrl: ticket.wsUrl,
            ticket: ticket.ticket,
            questionIds: script.questions.map((q) => q.id),
            mic: m,
            player: p,
            events,
            openSocket: await getSocketFactory(),
            location: wsLocation(),
          })
        } else {
          s = new TurnSession({
            instruction: script.instruction,
            questions: script.questions.map((q) => ({ id: q.id, text: q.text })),
            closing: script.closing,
            mic: m,
            player: p,
            events,
            tts: (text) => api.tts(briefing.id, round.n, text),
          })
        }
        session.current = s
        guard()
        const result = await s.run()
        pending.current = { clips: Object.fromEntries(Object.entries(result.clips).map(([qid, clip]) => [qid, clip.wav])), mode }
        await release()
        await submit()
      } catch (e) {
        await release()
        if (e instanceof SessionError && e.code === 'aborted') setState({ kind: 'ready' })
        else setState({ kind: 'failed', mode, error: e })
      }
    },
    // `events` is rebuilt every render but only closes over stable state setters and refs.
    [briefing.id, round, release, submit],
  )

  useEffect(
    () => () => {
      session.current?.abort()
      void mic.current?.close()
      void player.current?.close()
    },
    [],
  )

  return {
    state,
    captions,
    heard,
    start,
    finishAnswer: () => session.current?.finishAnswer(),
    abort: () => {
      aborted.current = true
      session.current?.abort()
    },
    reset: () => setState({ kind: 'ready' }),
    retrySubmit: () => void submit(),
    /** 0..1 level for the orb: the player while the phone speaks, the mic while the worker answers. */
    getLevel: (): number => {
      if (phase.current.kind === 'listening') return mic.current?.level ?? 0
      if (phase.current.kind === 'speaking') return player.current?.level ?? 0
      return 0
    },
  }
}
