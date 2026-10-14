/**
 * The briefing behind one start attempt. The first call creates it; every later call (a Retry after a failed
 * extract) patches the instruction of that same briefing instead of creating a second, empty record.
 *
 * `held` must be one object that lives as long as the screen (a ref's `.current`), not React state: the Retry
 * action of an error message keeps the closure of the render it was made in, and state there is stale.
 */
export async function saveStartBriefing(
  held: { id: string | null },
  instruction: string,
  io: {
    create: () => Promise<{ id: string }>
    patch: (id: string, instruction: string) => Promise<unknown>
  },
): Promise<string> {
  if (held.id) {
    await io.patch(held.id, instruction)
    return held.id
  }
  held.id = (await io.create()).id
  return held.id
}
