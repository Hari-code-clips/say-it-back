import { useEffect, useRef } from 'react'
import type { IconName } from '../../theme/iconNames.ts'
import { cx } from '../../ui/cx.ts'
import { Icon } from '../../ui/Icon.tsx'

export type OrbTone = 'speaking' | 'listening' | 'thinking' | 'idle'

const TONE: Record<OrbTone, { halo: string; ring: string; core: string }> = {
  speaking: { halo: 'bg-primary/15', ring: 'bg-primary/25', core: 'bg-primary text-on-primary' },
  listening: { halo: 'bg-success/15', ring: 'bg-success/25', core: 'bg-success text-on-success' },
  thinking: { halo: 'bg-secondary/10', ring: 'bg-secondary/15', core: 'bg-secondary text-on-secondary' },
  idle: { halo: 'bg-primary/10', ring: 'bg-primary/15', core: 'bg-primary-container text-on-primary-container' },
}

interface OrbProps {
  tone: OrbTone
  icon: IconName
  /** 0..1, polled every frame while speaking or listening. */
  getLevel: () => number
}

/**
 * The state indicator on the worker screen: the phone is talking (speaker), the worker's turn (mic, green), wait (hourglass).
 * The outer ring swells with the live audio level; with reduced motion it stays still and the colour, icon and word still
 * say what is happening.
 *
 * The swell never leaves the orb's own box: `.orb-ring` grows to 1.32x (index.css), so it rests at 76% of the box and tops
 * out at the box's edge. It used to rest at 100% and grow into the "Speak now" line under it.
 */
export function Orb({ tone, icon, getLevel }: OrbProps) {
  const ring = useRef<HTMLDivElement>(null)
  const live = tone === 'speaking' || tone === 'listening'

  useEffect(() => {
    if (!live) return
    let raf = 0
    const el = ring.current
    const tick = () => {
      el?.style.setProperty('--level', getLevel().toFixed(3))
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(raf)
      el?.style.setProperty('--level', '0')
    }
  }, [live, getLevel])

  const look = TONE[tone]
  return (
    // A screen that needs the room for something else (the worker screen's caption) sets --orb-size on a parent.
    <div aria-hidden="true" className="relative mx-auto grid size-[var(--orb-size,clamp(9rem,min(52vw,32dvh),16rem))] shrink-0 place-items-center">
      <div ref={ring} className={cx('orb-ring absolute inset-[12%] rounded-full transition-colors duration-200', look.halo)} />
      <div className={cx('absolute inset-[18%] rounded-full transition-colors duration-200', look.ring)} />
      <div
        className={cx(
          'relative grid size-[52%] place-items-center rounded-full shadow-elev-2 transition-colors duration-200',
          look.core,
          !live && 'animate-orb-breathe',
        )}
      >
        <Icon name={icon} filled className="text-[clamp(3rem,15vw,5rem)]" />
      </div>
    </div>
  )
}
