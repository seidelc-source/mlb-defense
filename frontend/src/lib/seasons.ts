/**
 * Merge one or more season lists into a single de-duplicated list, newest
 * first. Undefined inputs (e.g. queries that haven't resolved) are ignored.
 * Used to build the Player Profile season dropdown from fielding + pitching
 * data sources.
 */
export function mergeSeasons(...lists: Array<number[] | undefined>): number[] {
  const set = new Set<number>()
  for (const list of lists) {
    for (const season of list ?? []) set.add(season)
  }
  return [...set].sort((a, b) => b - a)
}
