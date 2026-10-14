import { core } from './en/core.ts'
import { flow } from './en/flow.ts'
import { pages } from './en/pages.ts'

/** English is the source table: every key is defined here, and Tamil and Chinese must match it. */
export const en = { ...core, ...flow, ...pages }

export type StringKey = keyof typeof en
export type Strings = Record<StringKey, string>
