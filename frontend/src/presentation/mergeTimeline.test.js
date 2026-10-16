import { expect, it } from 'vitest'
import { buildMergeTimeline } from './mergeTimeline'

it.each([
  [8, 3, 5, 1],
  [4, 4, 1, 1],
  [-2, 0, -9, 3]
])('归并演算保留每项身份，并生成有序结果：%j', (...values) => {
  const frames = buildMergeTimeline(values)
  for (const frame of frames) {
    expect(frame.tiles.map((tile) => tile.id).sort()).toEqual([0, 1, 2, 3])
    expect(frame.tiles.map((tile) => tile.value)).toEqual(values)
    expect(
      frame.tiles.every(
        (tile) => Number.isFinite(tile.x) && Number.isFinite(tile.y)
      )
    ).toBe(true)
    expect(frame.line).toBeGreaterThanOrEqual(1)
    expect(frame.line).toBeLessThanOrEqual(8)
    if (frame.line === 6)
      expect(frame.tiles.filter((tile) => tile.active)).toHaveLength(2)
  }
  const final = [...frames.at(-1).tiles].sort((a, b) => a.x - b.x)
  expect(final.map((tile) => tile.value)).toEqual(
    [...values].sort((a, b) => a - b)
  )
  expect(final.every((tile) => tile.sorted && tile.y === 350)).toBe(true)
})

it('重复数值保持稳定排序，生成的帧之间不共享可变对象', () => {
  const frames = buildMergeTimeline([2, 1, 2, 1])
  expect(
    [...frames.at(-1).tiles].sort((a, b) => a.x - b.x).map((tile) => tile.id)
  ).toEqual([1, 3, 0, 2])
  expect(frames[0].tiles[0]).not.toBe(frames[1].tiles[0])
  expect(() => buildMergeTimeline([1, 2])).toThrow('four-item')
})
