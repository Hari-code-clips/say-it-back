import { useEffect, useState } from 'react'
import { signalQuality, watchSignal, type NavigatorLike, type SignalQuality } from './connection.ts'

const read = (): SignalQuality => signalQuality(typeof navigator === 'undefined' ? undefined : (navigator as NavigatorLike))

/** The phone's signal as the browser reports it, kept current (see connection.ts: a hint, never a gate). */
export function useSignalQuality(): SignalQuality {
  const [quality, setQuality] = useState<SignalQuality>(read)
  useEffect(() => watchSignal(() => setQuality(read())), [])
  return quality
}
