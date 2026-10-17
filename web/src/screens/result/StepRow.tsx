/* Hallmark · component: a step's verdict row · genre: modern-minimal · theme: design.md
 * One row of a hairline list: the verdict chip (and a tag, when there is one) on a line of their own above the step's text, which then has
 * the whole row, at every width. The old chip | text | tag line squeezed the text to a word per line at 375 px (note 29, record bug), and
 * in Tamil even the 672 px row of a laptop left the text about 190 px, so there is no side-by-side layout to fall back to.
 * states: static (non-interactive); the row's controls, if any, are its own.
 */
import type { ReactNode } from 'react'
import type { Verdict } from '../../api/types.ts'
import { VerdictChip } from '../../ui/VerdictChip.tsx'
import { SampleTag } from './SampleTag.tsx'

interface Props {
  /** Absent for a step no model checked (2026-10-17, an in-person check): the row then shows no verdict chip. */
  verdict?: Verdict
  text: string
  /** BCP-47 tag of the step's text. */
  lang: string
  /** A status tag shown with the chip (for example "Open at decision"). */
  tag?: ReactNode
  /** The step was said back only by a stored sample answer. */
  sample?: boolean
}

export function StepRow({ verdict, text, lang, tag, sample }: Props) {
  return (
    <li className="space-y-2 px-4 py-3 sm:px-5">
      {(verdict || tag) && (
        <div className="flex flex-wrap items-center gap-2">
          {verdict && <VerdictChip verdict={verdict} />}
          {tag}
        </div>
      )}
      <p lang={lang} className="script-text min-w-0 text-body-lg text-on-surface">
        {text}
      </p>
      {sample && <SampleTag />}
    </li>
  )
}
