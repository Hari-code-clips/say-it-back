/* Hallmark · component: optional permit-to-work block · genre: modern-minimal · theme: design.md
 * Sits right under the task (the product is the check before a permit is released). One hairline card of rows: the switch, then, when it
 * is on, the permit number, the crew size and which worker this is. No filled panel inside the card.
 * states: off (default) · on: permit number (default · focus · error), crew size and worker chips (default · hover · focus-visible ·
 * checked). The checkbox is native: hover from .state-layer, focus from the global ring, accent from a token.
 */
import { CREW_MAX, clampSlot, permitRefValid } from '../../lib/permit.ts'
import { patchDraft, type Draft } from '../../flow/draft.ts'
import { useT } from '../../i18n/index.tsx'
import { Card, RowList, Section } from '../../ui/Card.tsx'
import { ChoiceChips } from '../../ui/Choice.tsx'
import { TextField } from '../../ui/TextField.tsx'

// A single digit in a chip is 43 px wide; the label keeps a minimum width so every chip is a 48 px target (design.md).
const numbers = (n: number) => Array.from({ length: n }, (_, i) => String(i + 1))
const digit = (n: string) => <span className="inline-block min-w-4 text-center tabular-nums">{n}</span>

/**
 * v0.5.2 (docs/API.md, "Permit-to-work grouping"): this briefing checks one worker on a high-risk permit. The permit
 * number, how many workers it covers, and which of them this is. A number, never a name or an ID (Rule 6).
 */
export function PermitBlock({ draft }: { draft: Draft }) {
  const t = useT()
  const permit = draft.permit ?? null
  const set = (patch: Partial<NonNullable<Draft['permit']>>) => {
    if (!permit) return
    const next = { ...permit, ...patch }
    patchDraft({ permit: { ...next, slot: clampSlot(next.slot, next.crewSize) } })
  }
  return (
    <Section title={t('start.permit')} hint={t('start.permitHint')} id="start-permit">
      <Card className="overflow-hidden">
        <RowList as="div">
          <label className="state-layer flex min-h-14 cursor-pointer items-center gap-3 px-4 py-2 sm:px-5">
            <input
              type="checkbox"
              checked={permit !== null}
              onChange={(e) => patchDraft({ permit: e.currentTarget.checked ? { ref: '', crewSize: 1, slot: 1 } : null })}
              className="size-5 shrink-0 cursor-pointer accent-primary"
            />
            <span className="text-body-lg text-on-surface">{t('start.permitOn')}</span>
          </label>

          {permit && (
            <>
              <div className="animate-fade-in px-4 pt-4 sm:px-5">
                <TextField
                  label={t('start.permitRef')}
                  value={permit.ref}
                  onChange={(ref) => set({ ref })}
                  maxLength={32}
                  autoComplete="off"
                  spellCheck={false}
                  helper={t('start.permitRefHelper')}
                  error={permit.ref.trim() && !permitRefValid(permit.ref) ? t('start.permitRefError') : undefined}
                />
              </div>
              <div className="animate-fade-in space-y-2 px-4 py-4 sm:px-5">
                <p className="text-title-sm text-on-surface-variant">{t('start.crewSize')}</p>
                <ChoiceChips
                  label={t('start.crewSize')}
                  value={String(permit.crewSize)}
                  onChange={(v) => set({ crewSize: Number(v) })}
                  options={numbers(CREW_MAX).map((n) => ({ value: n, label: digit(n) }))}
                />
              </div>
              <div className="animate-fade-in space-y-2 px-4 py-4 sm:px-5">
                <p className="text-title-sm text-on-surface-variant">{t('start.slot')}</p>
                <ChoiceChips
                  label={t('start.slot')}
                  value={String(permit.slot)}
                  onChange={(v) => set({ slot: Number(v) })}
                  options={numbers(permit.crewSize).map((n) => ({ value: n, label: digit(n) }))}
                />
                <p className="text-body-md text-on-surface-variant">{t('start.noName')}</p>
              </div>
            </>
          )}
        </RowList>
      </Card>
    </Section>
  )
}
