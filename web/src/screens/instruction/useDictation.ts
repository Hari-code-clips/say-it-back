import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/endpoints.ts'
import type { Lang } from '../../api/types.ts'
import { captureAnswer, type CaptureHandle } from '../../audio/capture.ts'
import { Mic } from '../../audio/mic.ts'

export type DictationState = 'idle' | 'starting' | 'recording' | 'transcribing'

const MIN_SPEECH_MS = 300
const MAX_MS = 60_000
/** The mic stays open briefly after release so the next press starts instantly. */
const KEEP_OPEN_MS = 8000

interface Options {
  lang: Lang
  onText: (text: string) => void
  /** MicError, ApiError, or the string 'too_short'. */
  onError: (error: unknown) => void
}

/**
 * Hold-to-speak for the supervisor's instruction: records on press, sends one WAV to
 * POST /api/transcribe on release, and hands the text back for editing.
 */
export function useDictation({ lang, onText, onError }: Options) {
  const [state, setStateRaw] = useState<DictationState>('idle')
  const stateRef = useRef<DictationState>('idle')
  const mic = useRef<Mic | null>(null)
  const capture = useRef<CaptureHandle | null>(null)
  const releaseRequested = useRef(false)
  const closeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const latest = useRef({ lang, onText, onError })
  latest.current = { lang, onText, onError }

  const setState = (next: DictationState) => {
    stateRef.current = next
    setStateRaw(next)
  }

  const scheduleClose = () => {
    clearTimeout(closeTimer.current)
    closeTimer.current = setTimeout(() => {
      void mic.current?.close()
      mic.current = null
    }, KEEP_OPEN_MS)
  }

  const start = useCallback(async () => {
    if (stateRef.current !== 'idle') return
    releaseRequested.current = false
    setState('starting')
    clearTimeout(closeTimer.current)
    try {
      mic.current ??= await Mic.open()
    } catch (e) {
      setState('idle')
      latest.current.onError(e)
      return
    }
    if (releaseRequested.current) {
      setState('idle')
      scheduleClose()
      return
    }
    const handle = captureAnswer(mic.current, { config: { silenceMs: Number.POSITIVE_INFINITY, maxMs: MAX_MS } })
    capture.current = handle
    setState('recording')
    const clip = await handle.done
    capture.current = null
    scheduleClose()
    if (clip.reason === 'abort') return setState('idle')
    if (clip.speechMs < MIN_SPEECH_MS) {
      setState('idle')
      latest.current.onError('too_short')
      return
    }
    setState('transcribing')
    try {
      const { text } = await api.transcribe(clip.wav, latest.current.lang)
      latest.current.onText(text.trim())
    } catch (e) {
      latest.current.onError(e)
    }
    setState('idle')
  }, [])

  const stop = useCallback(() => {
    releaseRequested.current = true
    capture.current?.finish('done')
  }, [])

  useEffect(
    () => () => {
      clearTimeout(closeTimer.current)
      capture.current?.finish('abort')
      void mic.current?.close()
    },
    [],
  )

  return { state, start, stop, getLevel: () => mic.current?.level ?? 0 }
}
