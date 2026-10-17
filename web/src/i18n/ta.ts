import type { Strings } from './en.ts'
import { core } from './ta/core.ts'
import { flow } from './ta/flow.ts'
import { pages } from './ta/pages.ts'
import { signal } from './ta/signal.ts'
import { privacy } from './ta/privacy.ts'
import { breadth } from './ta/breadth.ts'
import { judge } from './ta/judge.ts'
import { domains } from './ta/domains.ts'
import { inPerson } from './ta/inPerson.ts'

// DRAFT: Tamil strings are machine-written and need native-speaker review before real use.
// The type forces every key of the English table to be present.
export const ta: Strings = { ...core, ...flow, ...pages, ...signal, ...privacy, ...breadth, ...judge, ...domains, ...inPerson }
