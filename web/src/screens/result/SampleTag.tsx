/* Hallmark · component: stored-sample note (status, not a control) · genre: modern-minimal · theme: design.md
 * states: n/a (non-interactive): shown, or absent. A mark and a sentence, no fill: it sits inside rows and cards, which are the one layer.
 */
import { useT } from '../../i18n/index.tsx'
import { cx } from '../../ui/cx.ts'
import { Icon } from '../../ui/Icon.tsx'

/** "Said back by a stored sample answer, not the worker": beside a step's verdict, which stays as it was rated. */
export function SampleTag({ className }: { className?: string }) {
  const t = useT()
  return (
    <p className={cx('flex items-start gap-2 text-label-lg text-on-surface-variant', className)}>
      <Icon name="graphic_eq" className="mt-px text-[1.125rem]" />
      <span className="min-w-0">{t('sample.covered.tag')}</span>
    </p>
  )
}
