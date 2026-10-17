/* Hallmark · component: task picker · genre: modern-minimal · theme: design.md
 * One hairline card. Closed, it is the chosen task and one "Change task" row, so the permit block under it is on the first screen of a
 * phone. Open, both stay where they are and the tasks are native radios below them (arrows, Tab and screen readers come from the browser). A tap, Space or Enter on a task chooses it and closes the list; arrow keys only move the selection. Escape
 * closes. Focus goes to the first-checked task when the list opens and back to the row when it closes.
 * states: default · hover (state layer) · focus-visible (3 px ink ring, inset, instant) · active (state layer) · selected (fill + check)
 *         · expanded (`aria-expanded`) · disabled / loading / error / success n/a (a local choice; every task is always pickable).
 * 17 Oct (build-notes/37-domain-suites.md): open, the tasks sit under one quiet heading per work domain (`group`), ink-2 at 14 px on
 * the card face, a hairline above each group and none under its heading: no box, no tint, no uppercase. Each group is a labelled
 * group of the same native radios, so arrows still move through every task and a screen reader names the domain on entering it.
 */
import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { useT } from '../../i18n/index.tsx'
import { cx } from '../../ui/cx.ts'
import { Icon } from '../../ui/Icon.tsx'
import { groupByHeading, nextOpen } from './taskPickerState.ts'

export interface TaskOption {
  value: string
  icon: ReactNode
  title: string
  subtitle?: string
  /** Language tag of the title, e.g. "en". */
  lang?: string
  /** The heading this task is listed under (its work domain, in the UI language). */
  group?: string
}

interface Props {
  /** The id of the heading that names the group. */
  labelledBy: string
  value: string
  onChange: (value: string) => void
  options: readonly TaskOption[]
}

const FOCUS_INSET = 'focus-visible:outline-[3px] focus-visible:-outline-offset-[3px] focus-visible:outline-focus'

export function TaskPicker({ labelledBy, value, onChange, options }: Props) {
  const t = useT()
  const name = useId()
  const listId = useId()
  const [open, setOpen] = useState(false)
  const toggle = useRef<HTMLButtonElement>(null)
  const list = useRef<HTMLDivElement>(null)
  // True while an arrow key is moving the selection: its click must not close the list.
  const arrowing = useRef(false)
  const chosen = options.find((o) => o.value === value) ?? options[0]

  const set = (event: Parameters<typeof nextOpen>[1]) => {
    const next = nextOpen(open, event)
    setOpen(next)
    if (next === open) return
    // Move focus with the list: into it on open, back to the row on close (the radio it was on is gone).
    requestAnimationFrame(() => {
      const into = list.current?.querySelector<HTMLInputElement>('input:checked') ?? list.current?.querySelector<HTMLInputElement>('input')
      ;(next ? into : toggle.current)?.focus()
    })
  }

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key.startsWith('Arrow')) arrowing.current = true
    else if (e.key === 'Escape') {
      e.stopPropagation()
      set('escape')
    } else if (e.key === 'Enter' || e.key === ' ') {
      // Space on a radio that is already chosen does nothing natively, and Enter submits nothing here: both confirm the choice.
      e.preventDefault()
      if (!(e.target instanceof HTMLInputElement) || e.target.type !== 'radio') return
      onChange(e.target.value)
      set('pick')
    }
  }

  return (
    <div className="overflow-hidden rounded-lg border border-outline-variant bg-surface-container-lowest">
      <div className="flex min-h-16 items-center gap-4 px-4 py-3 max-[22.5rem]:gap-3 max-[22.5rem]:px-3 sm:px-5">
        <span className="grid size-6 shrink-0 place-items-center text-on-surface-variant">{chosen?.icon}</span>
        <span className="min-w-0 flex-1">
          <span lang={chosen?.lang} className="block text-title-md text-on-surface">
            {chosen?.title}
          </span>
          {chosen?.subtitle && <span className="block text-body-md text-on-surface-variant">{chosen.subtitle}</span>}
        </span>
      </div>
      <button
        ref={toggle}
        type="button"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => set('toggle')}
        className={cx('state-layer flex min-h-12 w-full items-center justify-between gap-3 border-t border-outline-variant px-4 text-left text-label-lg text-on-surface transition-colors sm:px-5', FOCUS_INSET)}
      >
        <span>{t('start.changeTask')}</span>
        <Icon name="expand_more" className={cx('shrink-0 transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div
          ref={list}
          id={listId}
          // A group of headed groups of one set of native radios (one `name`): a heading inside a radiogroup is not allowed.
          role="group"
          aria-labelledby={labelledBy}
          onKeyDown={onKeyDown}
          onKeyUp={() => {
            arrowing.current = false
          }}
          className="animate-fade-in divide-y divide-outline-variant border-t border-outline-variant"
        >
          {groupByHeading(options).map((g, i) => (
            <div key={g.heading ?? `group-${i}`} role={g.heading ? 'group' : undefined} aria-labelledby={g.heading ? `${listId}-g${i}` : undefined}>
              {g.heading && (
                <p id={`${listId}-g${i}`} className="px-4 pt-4 pb-1 text-title-sm text-on-surface-variant sm:px-5">
                  {g.heading}
                </p>
              )}
              <div className="divide-y divide-outline-variant">
                {g.items.map((o) => (
                  <TaskRadio key={o.value} option={o} name={name} checked={value === o.value} onChange={onChange} onClick={() => set(arrowing.current ? 'arrow' : 'pick')} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

interface RadioProps {
  option: TaskOption
  name: string
  checked: boolean
  onChange: (value: string) => void
  onClick: () => void
}

/** One task: a native radio (visually hidden) and its row. */
function TaskRadio({ option: o, name, checked, onChange, onClick }: RadioProps) {
  return (
    <label className="relative block cursor-pointer">
      <input
        type="radio"
        name={name}
        value={o.value}
        checked={checked}
        onChange={() => onChange(o.value)}
        // A pointer tap, Space or Enter closes the list; an arrow key's own click does not.
        onClick={onClick}
        className="peer sr-only"
      />
      <span
        className={cx(
          'state-layer flex min-h-16 items-center gap-4 px-4 py-3 transition-colors sm:px-5',
          'peer-focus-visible:outline-[3px] peer-focus-visible:-outline-offset-[3px] peer-focus-visible:outline-focus',
          checked && 'bg-secondary-container',
        )}
      >
        <span className="grid size-6 shrink-0 place-items-center text-on-surface-variant">{o.icon}</span>
        <span className="min-w-0 flex-1">
          <span lang={o.lang} className="block text-title-md text-on-surface">
            {o.title}
          </span>
          {o.subtitle && <span className="block text-body-md text-on-surface-variant">{o.subtitle}</span>}
        </span>
        <Icon name="check_circle" filled className={cx('text-primary transition-opacity', checked ? 'opacity-100' : 'opacity-0')} />
      </span>
    </label>
  )
}
