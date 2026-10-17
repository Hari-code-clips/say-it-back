/* Hallmark · component: named-phase bar · genre: modern-minimal · theme: design.md
 * Steps · Script · Worker · Result · Decision. From 600 px all five names, the current one in ink with a 2 px underline; on a phone a
 * dash per phase and only the current name (the others stay in the DOM for screen readers). No numbers: rounds are the only count.
 * Not interactive: no hover / active / disabled states. Position is word + weight + underline + aria-current, never colour alone.
 */
import { useT } from '../i18n/index.tsx'
import { cx } from '../ui/cx.ts'
import { phaseBar, type FlowStep } from './phases.ts'

export function PhaseBar({ step }: { step: FlowStep }) {
  const t = useT()
  const phases = phaseBar(step)
  // The Start form has no phase yet: the bar leaves its room empty so leave and language keep their places.
  if (phases.length === 0) return <div className="flex-1" />
  return (
    <nav aria-label={`${t('phasebar.label')}: ${t(`phase.${step}`)}`} className="min-w-0 flex-1 overflow-hidden px-2">
      <ol className="flex items-center gap-1 sm:gap-6">
        {phases.map(({ phase, state }) => (
          <li key={phase} aria-current={state === 'current' ? 'step' : undefined} className="flex min-w-0 items-center gap-1 sm:gap-2">
            <span
              aria-hidden="true"
              className={cx('h-1 shrink-0 rounded-full sm:hidden', state === 'current' ? 'w-5 bg-primary' : state === 'done' ? 'w-2 bg-primary' : 'w-2 bg-outline-variant')}
            />
            <span
              className={cx(
                'min-w-0 truncate py-1 text-label-lg',
                state === 'current' ? 'text-on-surface sm:border-b-2 sm:border-primary' : state === 'done' ? 'text-on-surface-variant max-sm:sr-only' : 'text-outline max-sm:sr-only',
              )}
            >
              {t(`phasebar.${phase}`)}
            </span>
          </li>
        ))}
      </ol>
    </nav>
  )
}
