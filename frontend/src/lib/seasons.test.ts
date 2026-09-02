import { describe, it, expect } from 'vitest'
import { mergeSeasons } from './seasons'

describe('mergeSeasons', () => {
  it('dedupes across lists and sorts newest first', () => {
    expect(mergeSeasons([2024, 2022], [2023, 2024])).toEqual([2024, 2023, 2022])
  })

  it('ignores undefined inputs (unresolved queries)', () => {
    expect(mergeSeasons(undefined, [2021, 2020])).toEqual([2021, 2020])
  })

  it('returns empty when there is no data', () => {
    expect(mergeSeasons(undefined, undefined)).toEqual([])
    expect(mergeSeasons([], [])).toEqual([])
  })

  it('sorts a single unordered list', () => {
    expect(mergeSeasons([2016, 2019, 2017])).toEqual([2019, 2017, 2016])
  })
})
