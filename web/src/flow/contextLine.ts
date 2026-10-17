// The one context line above a flow screen's title: "Crane lift · English → தமிழ் · Round 1 of 3".
// Plain text, no chips (web/design.md). Pure, so tests/flow/phaseBar.test.ts can pin the shape.

export const CONTEXT_SEPARATOR = ' · '

type Part = string | false | null | undefined

/** The parts that exist, trimmed. Empty and missing parts are dropped, so they leave no stray separator. */
export const contextParts = (parts: readonly Part[]): string[] => parts.map((p) => (typeof p === 'string' ? p.trim() : '')).filter(Boolean)

/** The parts, joined by a middle dot. */
export const contextLine = (parts: readonly Part[]): string => contextParts(parts).join(CONTEXT_SEPARATOR)

/** "English → தமிழ்". */
export const languagePair = (supervisor: string, worker: string): string => `${supervisor} → ${worker}`
