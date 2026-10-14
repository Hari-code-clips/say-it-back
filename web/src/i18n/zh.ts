import type { Strings } from './en.ts'
import { core } from './zh/core.ts'
import { flow } from './zh/flow.ts'
import { pages } from './zh/pages.ts'

// DRAFT: Chinese strings are machine-written and need native-speaker review before real use.
// The type forces every key of the English table to be present.
export const zh: Strings = { ...core, ...flow, ...pages }
