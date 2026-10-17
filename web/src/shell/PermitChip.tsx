/* Hallmark · component: permit-to-work chip (status, not a control) · genre: modern-minimal · theme: design.md
 * states: n/a (non-interactive). Word + icon, never colour alone.
 */
import type { PermitLink } from '../api/types.ts'
import { useUiLang } from '../i18n/index.tsx'
import { permitLabel } from '../lib/permit.ts'
import { StatusChip } from '../ui/Chip.tsx'

/** "PTW-123 · worker 2 of 3": which permit this briefing checks, and which worker on it (a number, never a name). */
export function PermitChip({ permit, className }: { permit: PermitLink; className?: string }) {
  const { lang } = useUiLang()
  return (
    <StatusChip icon="description" className={className}>
      <span className="[overflow-wrap:anywhere]">{permitLabel(permit, lang)}</span>
    </StatusChip>
  )
}
