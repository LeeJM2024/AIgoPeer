import { afterEach, expect, it, vi } from 'vitest'
import {
  assignmentAction,
  assignmentArt,
  assignmentDestination,
  pendingAssignments
} from './assignments'
afterEach(() => vi.useRealTimers())

it('按真实主题选择插画，不把无关题目画成归并排序', () => {
  expect(assignmentArt({ title: '归并排序' })).toBe('merge')
  expect(assignmentArt({ title: '0/1 背包' })).toBe('dp')
  expect(assignmentArt({ title: 'Dijkstra 最短路径' })).toBe('graph')
  expect(assignmentArt({ title: '二叉树遍历' })).toBe('tree')
  expect(assignmentArt({ title: '整数求和' })).toBe('sum')
  expect(assignmentArt({ title: '未识别的题目' })).toBe('code')
  expect(assignmentArt({ title: '算法微课', type: 'FINAL_PROJECT' })).toBe(
    'lesson'
  )
})

it('待办只选择开放且尚未完成的作业，截止近者优先', () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-16T00:00:00Z'))
  const base = {
    type: 'PROGRAMMING',
    status: 'PUBLISHED',
    submit_deadline: '2026-10-18T00:00:00Z'
  }
  const items = [
    { ...base, id: 1 },
    {
      ...base,
      id: 2,
      submit_deadline: '2026-10-17T00:00:00Z',
      submission: { status: 'WA' }
    },
    { ...base, id: 3, submission: { status: 'AC' } },
    { ...base, id: 4, submission: { status: 'QUEUED' } },
    { ...base, id: 5, submit_deadline: '2026-10-15T00:00:00Z' },
    { ...base, id: 6, status: 'PUBLISHED_RESULT' },
    { ...base, id: 7, type: 'FINAL_PROJECT', submission: { status: 'VALID' } },
    {
      ...base,
      id: 8,
      type: 'FINAL_PROJECT',
      submission: { status: 'SUBMITTED', material_check_status: 'INVALID' }
    }
  ]
  expect(pendingAssignments(items).map((item) => item.id)).toEqual([2, 1, 8])
  expect(items[0].id).toBe(1)
})

it('未发布项目不会展示查分入口，截止后的材料仍可查阅', () => {
  const item = {
    id: 3,
    type: 'FINAL_PROJECT',
    status: 'TEACHER_GRADING',
    submit_deadline: '2020-01-01'
  }
  expect(assignmentAction(item)).toBe('查看提交与材料检查')
  expect(assignmentDestination(item)).toBe(
    '/student/assignments/3/project-submission'
  )
  expect(assignmentDestination({ ...item, status: 'PUBLISHED_RESULT' })).toBe(
    '/student/assignments/3/grade'
  )
})
