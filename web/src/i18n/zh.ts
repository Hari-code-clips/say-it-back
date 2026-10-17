import type { Strings } from './en.ts'
import { core } from './zh/core.ts'
import { flow } from './zh/flow.ts'
import { pages } from './zh/pages.ts'
import { signal } from './zh/signal.ts'
import { privacy } from './zh/privacy.ts'
import { breadth } from './zh/breadth.ts'
import { judge } from './zh/judge.ts'
import { domains } from './zh/domains.ts'
import { inPerson } from './zh/inPerson.ts'

// DRAFT: Chinese strings are machine-written and need native-speaker review before real use.
// The type forces every key of the English table to be present.
export const zh: Strings = { ...core, ...flow, ...pages, ...signal, ...privacy, ...breadth, ...judge, ...domains, ...inPerson }
