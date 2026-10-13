// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import ProgrammingSubmissionHistory from './ProgrammingSubmissionHistory.vue'
import * as api from '../../api/student/programmingSubmissions'

vi.mock('../../api/student/programmingSubmissions', () => ({ getCodeSubmissionHistory: vi.fn(), getCodeSubmission: vi.fn() }))
const wrappers = []
const open = () => {
  const wrapper = mount(ProgrammingSubmissionHistory, { props: { assignmentId: '6' } })
  wrappers.push(wrapper)
  return wrapper
}
const record = (id, current = false) => ({ id, version: id, status: 'AC', is_current: current, submitted_at: '2026-10-13T06:00:00Z' })
beforeEach(() => {
  vi.resetAllMocks()
  api.getCodeSubmissionHistory.mockResolvedValue({ items: [record(8, true), record(7)], total: 8, page: 1 })
})
afterEach(() => wrappers.splice(0).forEach((w) => w.unmount()))

it('显示当前版本标记、顺序与分页，翻页不重新指定当前提交', async () => {
  const wrapper = open()
  await flushPromises()
  expect(wrapper.get('tbody tr').text()).toContain('第 8 次当前版本')
  expect(wrapper.emitted('current')[0][0].id).toBe(8)
  api.getCodeSubmissionHistory.mockResolvedValue({ items: [record(3), record(2), record(1)], total: 8, page: 2 })
  await wrapper.findAll('button').find((b) => b.text() === '下一页').trigger('click')
  await flushPromises()
  expect(api.getCodeSubmissionHistory).toHaveBeenLastCalledWith('6', 2, 5)
  expect(wrapper.text()).toContain('第 2 / 2 页')
  expect(wrapper.emitted('current')).toHaveLength(1)
})

it('空历史不请求不存在的判题详情', async () => {
  api.getCodeSubmissionHistory.mockResolvedValue({ items: [], total: 0, page: 1 })
  const wrapper = open()
  await flushPromises()
  expect(wrapper.text()).toContain('暂无提交记录')
  expect(api.getCodeSubmission).not.toHaveBeenCalled()
})

it('历史加载失败可以重试，并保留当前页', async () => {
  const wrapper = open()
  await flushPromises()
  api.getCodeSubmissionHistory.mockRejectedValueOnce(new Error('服务暂不可用'))
  await wrapper.findAll('button').find((b) => b.text() === '下一页').trigger('click')
  await flushPromises()
  expect(wrapper.get('[role=alert]').text()).toContain('服务暂不可用')
  expect(wrapper.text()).toContain('第 1 / 2 页')
  await wrapper.findAll('button').find((b) => b.text() === '刷新提交历史').trigger('click')
  await flushPromises()
  expect(wrapper.find('[role=alert]').exists()).toBe(false)
})

it('切换详情时只显示最后选择的响应，编译诊断按文本渲染', async () => {
  let resolveOld
  api.getCodeSubmission.mockImplementation((id) => id === 8
    ? new Promise((resolve) => { resolveOld = resolve })
    : Promise.resolve({ id: 7, version: 7, status: 'CE', compiler_output: '<script>bad()</script>', passed_case_count: 0, executed_case_count: 0 }))
  const wrapper = open()
  await flushPromises()
  await wrapper.get('button[aria-label="查看第 8 次提交结果"]').trigger('click')
  await wrapper.get('button[aria-label="查看第 7 次提交结果"]').trigger('click')
  await flushPromises()
  resolveOld({ id: 8, version: 8, status: 'AC' })
  await flushPromises()
  expect(wrapper.get('.history-detail').text()).toContain('第 7 次提交')
  expect(wrapper.get('.compiler-output').text()).toBe('<script>bad()</script>')
  expect(wrapper.find('.compiler-output script').exists()).toBe(false)
})

it('详情查询失败允许重试，不重新提交或判题', async () => {
  api.getCodeSubmission.mockRejectedValueOnce(new Error('查询失败')).mockResolvedValue({ id: 7, version: 7, status: 'WA' })
  const wrapper = open()
  await flushPromises()
  await wrapper.get('button[aria-label="查看第 7 次提交结果"]').trigger('click')
  await flushPromises()
  expect(wrapper.get('[role=alert]').text()).toContain('查询失败')
  await wrapper.findAll('button').find((b) => b.text() === '重试判题详情').trigger('click')
  await flushPromises()
  expect(wrapper.get('.history-detail').text()).toContain('答案错误')
  expect(api.getCodeSubmission).toHaveBeenCalledTimes(2)
})
