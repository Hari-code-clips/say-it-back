import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, wsLocation } from '../../api/client.ts'
import { api } from '../../api/endpoints.ts'
import type { Briefing, Round } from '../../api/types.ts'
import { clipKey, saveClips } from '../../audio/clips.ts'
import { ClipSource } from '../../audio/clipSource.ts'
import { Mic } from '../../audio/mic.ts'
import { Player } from '../../audio/player.ts'
import { LiveSession } from '../../live/liveSession.ts'
import { SessionError, type BriefingSession, type StageEvents, type StagePhase } from '../../live/session.ts'
import { getSocketFactory } from '../../live/socket.ts'
import { TurnSession } from '../../live/turnSession.ts'
import { decodeWavTo16k } from '../../audio/wav.ts'
import { newUploadKey, uploads } from '../../net/queue.ts'
import { untilAnswered, type Waiting } from '../../net/retry.ts'
import { needsConsent } from './consentFlow.ts'
import { sampleStillWanted, shouldAutoPlay } from './sample.ts'
import type { ReportSource } from './useHazardReport.ts'

export type RunMode = 'live' | 'turn'

/** The stored sample answer in the current answer window: fetching it, playing it, done, or it could not be played. */
export type SampleState = 'idle' | 'loading' | 'playing' | 'used' | 'failed' | 'dropped'

/** The first sample of the run that could not be played, or came too late: said once, at the check's wait. */
export type SampleIssue = 'failed' | 'dropped' | null

export type RunState =
  | { kind: 'ready' }
  | { kind: 'running'; mode: RunMode; phase: StagePhase }
  | { kind: 'failed'; mode: RunMode; error: unknown }
  | { kind: 'submitting' }
  | { kind: 'submit_failed'; error: unknown }

interface Options {
  briefing: Briefing
  round: Round
  /**
   * The round was judged (the check succeeded, or the server had already finished it). It must NOT re-read the briefing into the
   * route's state: a judged briefing is redirected to the result at once, and the result opens only when the supervisor has the phone.
   */
  onJudged: () => Promise<void>
  /** The stored synthetic answer's clip for a question of this round (endpoint 24); undefined for a question with none. */
  sample?: (qid: string) => Promise<Blob> | undefined
  /**
   * F1: the questions whose answer window gets the stored sample the moment it opens (the supervisor chose "Use stored sample
   * answers for this round" on the handover step). Empty: every answer is the worker's voice. See sample.ts `sampleQids` and `shouldAutoPlay`.
   */
  sampleQids?: readonly string[]
}

/**
 * Runs one briefing round: opens the player and mic from the tap that started it, runs the Live or
 * Turn session, then POSTs the per-question WAVs to /check. If Live fails, the same round can be
 * run again in Turn mode.
 */
export function useBriefingRun({ briefing, round, onJudged, sample, sampleQids = [] }: Options) {
  const [state, setState] = useState<RunState>({ kind: 'ready' })
  // When the check request went out (the last answer was in): the wait counts from here, not from the supervisor's tap.
  const [submittedAt, setSubmittedAt] = useState<number | null>(null)
  const autoQids = useRef(sampleQids)
  autoQids.current = sampleQids
  const autoPlay = useRef<() => void>(() => undefined)
  const [captions, setCaptions] = useState({ model: '', worker: '' })
  const [heard, setHeard] = useState(false)
  const [sampleState, setSampleState] = useState<SampleState>('idle')
  const [sampleIssue, setSampleIssue] = useState<SampleIssue>(null)
  const clip = useRef<ClipSource | null>(null)
  const sampleAudio = useRef<{ el: HTMLAudioElement; url: string } | null>(null)
  const session = useRef<BriefingSession | null>(null)
  const mic = useRef<Mic | null>(null)
  const player = useRef<Player | null>(null)
  const phase = useRef<StagePhase>({ kind: 'connecting' })
  const pending = useRef<{ clips: Record<string, Blob>; mode: RunMode; sampleAnswers: string[]; key: string } | null>(null)
  // 2026-10-16 signal: while the check upload waits for a signal (null when it is not waiting), and how to stop that wait.
  const [waiting, setWaiting] = useState<Waiting | null>(null)
  const submitStop = useRef<AbortController | null>(null)
  const modeRef = useRef<RunMode>('live')
  // "End round" can be tapped while the mic is still opening or the ticket is being fetched, before
  // a session exists to abort. The flag is checked between the start-up steps.
  const aborted = useRef(false)
  const guard = () => {
    if (aborted.current) throw new SessionError('aborted', 'The briefing was ended.')
  }

  /** Stop the sample's playback (the window it was played into has ended). */
  const stopSample = useCallback(() => {
    const a = sampleAudio.current
    sampleAudio.current = null
    clip.current = null
    if (a) {
      a.el.pause()
      URL.revokeObjectURL(a.url)
    }
  }, [])

  const release = useCallback(async () => {
    stopSample()
    session.current = null
    const m = mic.current
    const p = player.current
    mic.current = null
    player.current = null
    await Promise.all([m?.close(), p?.close()])
  }, [])

  const events: StageEvents = {
    onPhase: (next) => {
      if (phase.current.kind === 'listening' && next.kind !== 'listening' && clip.current) {
        stopSample()
        setSampleState('used')
      }
      phase.current = next
      setState({ kind: 'running', mode: modeRef.current, phase: next })
      if (next.kind === 'speaking') setCaptions((c) => ({ ...c, model: '' }))
      if (next.kind === 'listening') {
        setCaptions((c) => ({ ...c, worker: '' }))
        setHeard(false)
        // F1: a question that has a stored sample, when the supervisor chose it for this round, gets the clip as its window opens.
        // A microtask later, so the session has opened the window (it announces the phase just before it does).
        if (shouldAutoPlay(autoQids.current, next)) queueMicrotask(() => autoPlay.current())
      }
    },
    onCaption: (role, text) => setCaptions((c) => ({ ...c, [role]: text })),
    onSpeech: setHeard,
  }

  const submit = useCallback(async () => {
    const job = pending.current
    if (!job) return
    setState({ kind: 'submitting' })
    setSubmittedAt(Date.now())
    saveClips(clipKey(briefing.id, round.n), job.clips)
    // 2026-10-16 signal: with no answer from the server (offline, a dropped connection, a timeout) the upload is sent again by
    // itself, with backoff, under the same Idempotency-Key; the answers stay on the phone (src/net/queue.ts) until it has an answer.
    const stop = new AbortController()
    submitStop.current = stop
    const judgedNow = async () => {
      void uploads.drop(briefing.id, round.n)
      await onJudged()
    }
    try {
      await untilAnswered(() => api.check(briefing.id, round.n, job.clips, job.mode, job.sampleAnswers, job.key), { onWait: setWaiting, signal: stop.signal })
    } catch (e) {
      if (stop.signal.aborted) return // the screen was left: the job stays on the phone for the next visit
      // The server may have finished after the client gave up (a timeout, a dropped connection): look before retrying. Looked at
      // with a plain read, not the route's refresh: a judged briefing in the route's state would open the result on its own.
      const judgedAlready = e instanceof ApiError && e.code === 'invalid_state'
      const fresh = judgedAlready ? undefined : await api.getBriefing(briefing.id).catch(() => undefined)
      if (judgedAlready || (fresh && fresh.status !== 'briefing')) return judgedNow()
      setState({ kind: 'submit_failed', error: e })
      return
    }
    await judgedNow()
  }, [briefing.id, round.n, onJudged])

  // A reload or a crashed tab after the last answer: the check upload still owed for this round is sent again (src/net/queue.ts).
  // The latest `submit` is read from a ref: the screen's `onJudged` is a new function each render, and a re-run of this effect must
  // never stop an upload that is waiting for a signal. The wait stops only when the screen is left.
  const submitLatest = useRef(submit)
  submitLatest.current = submit
  useEffect(() => {
    let live = true
    void uploads.load(briefing.id, round.n).then((job) => {
      if (!live || !job || pending.current) return
      pending.current = { clips: job.clips, mode: job.mode, sampleAnswers: job.sampleAnswers, key: job.key }
      void submitLatest.current()
    })
    return () => {
      live = false
    }
  }, [briefing.id, round.n])
  useEffect(() => () => submitStop.current?.abort(), [])

  const start = useCallback(
    async (mode: RunMode) => {
      modeRef.current = mode
      aborted.current = false
      phase.current = { kind: 'connecting' }
      setSampleState('idle')
      setSampleIssue(null)
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
          // Security fixes B: the ticket declares a samples-only session exactly when no consent screen was shown (consentFlow.ts).
          const samplesOnly = !needsConsent(script.questions.map((q) => q.id), autoQids.current)
          const ticket = await api.liveSession(briefing.id, round.n, samplesOnly)
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
        const job = {
          clips: Object.fromEntries(Object.entries(result.clips).map(([qid, answer]) => [qid, answer.wav])),
          mode,
          sampleAnswers: result.sampleAnswers,
          key: newUploadKey(),
        }
        pending.current = job
        await uploads.save({ ...job, briefingId: briefing.id, n: round.n, savedAt: Date.now() })
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
      stopSample()
      void mic.current?.close()
      void player.current?.close()
    },
    [stopSample],
  )

  /**
   * The stored sample answer (synthetic voice): the clip is played into the open answer window instead of the mic (Live: streamed on
   * the socket at real-time pace; Turn: recorded as the WAV), and is heard on the phone as it plays. Called as the window of a
   * question that has a stored sample opens, when the supervisor chose it for the round (`sampleQids`); each question gets its own
   * clip (`sample(qid)`).
   */
  const playSample = useCallback(async () => {
    const s = session.current
    // The question it is tapped for, fixed now: the clip may arrive after that window has closed (v0.4 review).
    const tapped = phase.current.kind === 'listening' ? phase.current.qid : null
    const fetching = tapped === null ? undefined : sample?.(tapped) // this question's clip, fetched ahead of the choice
    if (!fetching || !s || tapped === null || clip.current) return
    setSampleState('loading')
    try {
      const blob = await fetching
      const pcm = decodeWavTo16k(new Uint8Array(await blob.arrayBuffer()))
      if (!pcm || pcm.length === 0) throw new Error('The sample answer is not a 16-bit PCM WAV.')
      const source = new ClipSource(pcm)
      // Only into the window it was tapped for. Late, it is dropped with a note, never played into the next question.
      if (!sampleStillWanted(tapped, phase.current) || !s.useSample(source, tapped)) {
        setSampleState('dropped')
        setSampleIssue((issue) => issue ?? 'dropped')
        return
      }
      clip.current = source
      const url = URL.createObjectURL(blob)
      const el = new Audio(url)
      sampleAudio.current = { el, url }
      void el.play().catch(() => undefined) // heard on the phone; what is judged is the PCM sent above
      setSampleState('playing')
    } catch {
      setSampleState('failed')
      setSampleIssue((issue) => issue ?? 'failed')
    }
  }, [sample])

  autoPlay.current = () => void playSample()

  /** The worker's problem report: the briefing's own mic while it runs (the side sink), else one opened for the report. */
  const reportSource = useCallback(async (): Promise<ReportSource> => {
    const m = mic.current
    if (m) return { source: m.side, release: async () => undefined }
    const own = await Mic.open()
    return { source: own, release: () => own.close() }
  }, [])

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
    /** When the check request last went out (Date.now()); null before the first. */
    submittedAt,
    /** The check upload is waiting for a signal to be sent again (2026-10-16); null when it is not. */
    waiting,
    sampleState,
    /** A sample of this run that failed or came late, in any window (the per-window state above moves on to the next). */
    sampleIssue,
    reportSource,
    /** 0..1 level for the orb: the player while the phone speaks, the mic while the worker answers. */
    getLevel: (): number => {
      if (phase.current.kind === 'listening') return clip.current?.level ?? mic.current?.level ?? 0
      if (phase.current.kind === 'speaking') return player.current?.level ?? 0
      return 0
    },
  }
}
