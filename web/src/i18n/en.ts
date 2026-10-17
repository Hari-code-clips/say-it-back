import { core } from './en/core.ts'
import { flow } from './en/flow.ts'
import { pages } from './en/pages.ts'
import { signal } from './en/signal.ts'
import { privacy } from './en/privacy.ts'
import { breadth } from './en/breadth.ts'
import { judge } from './en/judge.ts'
import { domains } from './en/domains.ts'
import { inPerson } from './en/inPerson.ts'

/** English is the source table: every key is defined here, and Tamil and Chinese must match it. */
export const en = { ...core, ...flow, ...pages, ...signal, ...privacy, ...breadth, ...judge, ...domains, ...inPerson }

export type StringKey = keyof typeof en
export type Strings = Record<StringKey, string>
