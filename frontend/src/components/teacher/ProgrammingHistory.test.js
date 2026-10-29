// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import ProgrammingHistory from './ProgrammingHistory.vue'
import { getProgrammingHistory } from '../../api/teacher'
vi.mock('../../api/teacher', () => ({ getProgrammingHistory: vi.fn() }))
beforeEach(() => {
  vi.resetAllMocks()
  getProgrammingHistory.mockResolvedValue({ total: 21, page: 1, items: [{ id: 1, student_no: 'S1', name: '同学', class_name: '一班', version: 1, status: 'CE', queued_at: '2026-10-22', source_code: '<img src=x onerror=bad()>', compiler_output: 'syntax error', time_ms: null, memory_kb: null, passed_case_count: 0, executed_case_count: 0 }] })
})
it('教师可查看旧版本源码、编译反馈，并按学生筛选与分页', async () => {
  const w = mount(ProgrammingHistory, { props: { assignmentId: 7, students: [{ id: 2, student_no: 'S1', name: '同学' }] } }); await flushPromises()
  await w.findAll('button').find(b => b.text() === '查看提交 1').trigger('click')
  expect(w.text()).toContain('syntax error')
  expect(w.get('pre').text()).toContain('<img')
  expect(w.find('img').exists()).toBe(false)
  await w.findAll('button').find(b => b.text() === '下一页').trigger('click'); await flushPromises()
  expect(getProgrammingHistory).toHaveBeenLastCalledWith(7, 2, '')
  await w.get('select').setValue(2); await flushPromises()
  expect(getProgrammingHistory).toHaveBeenLastCalledWith(7, 1, 2)
  w.unmount()
})
