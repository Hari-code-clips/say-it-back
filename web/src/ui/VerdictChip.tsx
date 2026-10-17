/* Hallmark · component: verdict chip · genre: modern-minimal · theme: design.md ("chroma means a verdict")
 * Got it: green tint + check. Ask again: amber tint + refresh. Wrong: solid red + close. Missed: no fill, 2 px ink outline + an outlined
 * minus-in-circle. Word + mark + treatment, so Missed is visibly different from Wrong with no colour at all. Not interactive.
 */
import type { Verdict } from '../api/types.ts'
import { useT, type StringKey } from '../i18n/index.tsx'
import { FLAG_LABEL, VERDICT } from '../screens/result/verdict.ts'
import { StatusChip } from './Chip.tsx'

/** "Got it" / "Missed" / "Wrong" / "Ask again": mark + word + treatment. */
export function VerdictChip({ verdict, className }: { verdict: Verdict; className?: string }) {
  const t = useT()
  const look = VERDICT[verdict]
  return (
    <StatusChip tone={look.tone} icon={look.icon} className={className}>
      {t(look.label)}
    </StatusChip>
  )
}

/** A small neutral chip for a rating or transcript flag. */
export function FlagChip({ flag }: { flag: string }) {
  const t = useT()
  const key: StringKey | undefined = FLAG_LABEL[flag]
  return <StatusChip icon="flag">{key ? t(key) : flag}</StatusChip>
}
