/* Hallmark · component: hold-to-speak · genre: modern-minimal · theme: design.md
 * states: default (outlined) · hover (state layer) · focus-visible (ring) · active (state layer) · disabled (transcribing) ·
 *         loading (starting / transcribing spinner) · recording (ink fill and the level ring) · error and success are the snackbar's.
 */

import { useEffect, useRef } from 'react'
import { useT } from '../../i18n/index.tsx'
import { cx } from '../../ui/cx.ts'
import { Icon } from '../../ui/Icon.tsx'
import { Spinner } from '../../ui/Feedback.tsx'
import type { DictationState } from './useDictation.ts'

interface HoldToSpeakProps {
  state: DictationState
  start: () => void
  stop: () => void
  getLevel: () => number
}

/**
 * Press and hold to record, release to send. Pointer users hold; keyboard and screen-reader users,
 * whose activation arrives as a click, toggle instead (press to start, press again to stop).
 */
export function HoldToSpeak({ state, start, stop, getLevel }: HoldToSpeakProps) {
  const t = useT()
  const ring = useRef<HTMLSpanElement>(null)
  const viaPointer = useRef(false)
  const recording = state === 'recording'
  const busy = state === 'transcribing'

  // Level ring: written straight to the element, not through React state.
  useEffect(() => {
    if (!recording) return
    let raf = 0
    const tick = () => {
      ring.current?.style.setProperty('--level', getLevel().toFixed(3))
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [recording, getLevel])

  const label =
    state === 'starting' ? t('instr.starting') : recording ? t('instr.listening') : busy ? t('instr.transcribing') : t('instr.hold')

  return (
    <button
      type="button"
      aria-pressed={recording}
      disabled={busy}
      onPointerDown={(e) => {
        if (e.button !== 0) return // primary button, touch or pen only
        viaPointer.current = true
        e.currentTarget.setPointerCapture(e.pointerId)
        start()
      }}
      onPointerUp={stop}
      onPointerCancel={() => {
        viaPointer.current = false
        stop()
      }}
      onClick={() => {
        if (viaPointer.current) {
          viaPointer.current = false
          return
        }
        if (recording) stop()
        else start()
      }}
      onContextMenu={(e) => e.preventDefault()}
      className={cx(
        // 360 px and below: less padding and gap, so every state's label keeps to one line.
        // 12 px corners, not a pill (design.md). Idle: an outlined control; recording: ink fill, the one state that is "on".
        'state-layer no-select inline-flex min-h-16 items-center gap-3 rounded-md border-[1.5px] px-6 text-title-md transition-colors max-[22.5rem]:gap-2 max-[22.5rem]:px-4',
        recording ? 'border-primary bg-primary text-on-primary' : 'border-outline bg-transparent text-on-surface',
        busy && 'opacity-80',
      )}
    >
      <span className="relative grid size-10 place-items-center">
        {recording && <span ref={ring} aria-hidden="true" className="orb-ring absolute inset-0 rounded-full bg-on-primary/25" />}
        {busy ? <Spinner className="border-current border-t-transparent" /> : <Icon name="mic" filled={recording} className="relative text-[1.75rem]" />}
      </span>
      <span>{label}</span>
    </button>
  )
}
