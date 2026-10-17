import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from './Button.tsx'

interface ClipPlayerProps {
  /** A clip already in memory (the worker's answer), or a loader that fetches it on first play. */
  blob?: Blob
  load?: () => Promise<Blob>
  playLabel: string
  stopLabel: string
  className?: string
}

interface Handle {
  stop: () => void
}

// Only one clip plays at a time.
let current: Handle | null = null

export function ClipPlayer({ blob, load, playLabel, stopLabel, className }: ClipPlayerProps) {
  const [state, setState] = useState<'idle' | 'loading' | 'playing'>('idle')
  const audio = useRef<HTMLAudioElement | null>(null)
  const url = useRef<string | null>(null)
  const handle = useRef<Handle>({ stop: () => undefined })

  const stop = useCallback(() => {
    audio.current?.pause()
    audio.current = null
    if (url.current) URL.revokeObjectURL(url.current)
    url.current = null
    if (current === handle.current) current = null
    setState('idle')
  }, [])
  handle.current.stop = stop

  // Release the object URL when the card goes away.
  useEffect(() => {
    const h = handle.current
    return () => h.stop()
  }, [])

  const play = async () => {
    current?.stop()
    current = handle.current
    setState('loading')
    try {
      const data = blob ?? (await load?.())
      if (!data) return stop()
      url.current = URL.createObjectURL(data)
      const el = new Audio(url.current)
      audio.current = el
      el.onended = stop
      await el.play()
      setState('playing')
    } catch {
      stop()
    }
  }

  return (
    <Button
      variant="outlined"
      icon={state === 'playing' ? 'stop' : 'play_arrow'}
      busy={state === 'loading'}
      onClick={state === 'playing' ? stop : play}
      className={className}
    >
      {state === 'playing' ? stopLabel : playLabel}
    </Button>
  )
}
