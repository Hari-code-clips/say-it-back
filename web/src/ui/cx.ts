export type ClassValue = string | false | null | undefined

/** Joins truthy class names. */
export const cx = (...values: ClassValue[]): string => values.filter(Boolean).join(' ')
