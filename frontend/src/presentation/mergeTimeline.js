// Actual merge-sort trace, expressed as tile positions for the course poster.
export function buildMergeTimeline(values = [8, 3, 5, 1]) {
  if (values.length !== 4)
    throw new Error('The course poster uses a four-item array.')
  const items = values.map((value, id) => ({ id, value }))
  const position = (start, length, depth, index) => {
    if (depth === 0) return { x: 193 + index * 72, y: 350 }
    if (depth === 1) return { x: (start === 0 ? 72 : 465) + index * 72, y: 170 }
    return { x: [35, 205, 435, 605][start], y: 275 }
  }
  let tiles = items.map((item, index) => ({
    ...item,
    x: 193 + index * 72,
    y: 54,
    active: false,
    sorted: false
  }))
  const frames = []
  const capture = (label, line, active = []) => {
    tiles = tiles.map((tile) => ({ ...tile, active: active.includes(tile.id) }))
    frames.push({ label, line, tiles: tiles.map((tile) => ({ ...tile })) })
  }
  capture('从无序数组开始', 1)
  function sort(group, start, depth) {
    if (group.length < 2) {
      capture(`子问题只剩 ${group[0].value}，直接返回`, 2, [group[0].id])
      return group
    }
    const middle = group.length / 2
    group.forEach((item, index) =>
      Object.assign(
        tiles.find((tile) => tile.id === item.id),
        position(
          start + (index < middle ? 0 : middle),
          middle,
          depth + 1,
          index % middle
        )
      )
    )
    capture(
      `把 ${group.map((item) => item.value).join('、')} 拆成两个子问题`,
      3,
      group.map((item) => item.id)
    )
    capture(
      '递归处理左侧子数组',
      4,
      group.slice(0, middle).map((item) => item.id)
    )
    const left = sort(group.slice(0, middle), start, depth + 1)
    capture(
      '递归处理右侧子数组',
      5,
      group.slice(middle).map((item) => item.id)
    )
    const right = sort(group.slice(middle), start + middle, depth + 1)
    let l = 0,
      r = 0
    const result = []
    while (l < left.length || r < right.length) {
      if (l < left.length && r < right.length)
        capture(
          `比较 ${left[l].value} 与 ${right[r].value}，选择较小的一项`,
          6,
          [left[l].id, right[r].id]
        )
      const next =
        r >= right.length ||
        (l < left.length && left[l].value <= right[r].value)
          ? left[l++]
          : right[r++]
      const target = tiles.find((tile) => tile.id === next.id)
      Object.assign(
        target,
        position(start, group.length, depth, result.length),
        { sorted: true }
      )
      result.push(next)
      capture(
        `将 ${next.value} 放入${depth === 0 ? '最终' : '当前'}有序数组`,
        7,
        [next.id]
      )
    }
    return result
  }
  const sorted = sort(items, 0, 0)
  capture(`归并完成：${sorted.map((item) => item.value).join('、')}`, 8)
  return frames
}
