// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import StudentProgrammingSubmissionView from './StudentProgrammingSubmissionView.vue'
import * as api from '../../api/student/programmingSubmissions'
import { currentUser } from '../../api/auth'
import * as ai from '../../api/ai'

vi.mock('vue-router', () => ({ RouterLink: { template: '<a><slot /></a>' } }))
vi.mock('../../api/auth', () => ({ currentUser: vi.fn() }))
vi.mock('../../api/ai', () => ({ getStudentAiStatus: vi.fn(), getAiHistory: vi.fn(), askAi: vi.fn() }))
vi.mock('../../api/student/programmingSubmissions', () => ({
  getProgrammingProblem: vi.fn(), submitCode: vi.fn(), getCodeSubmission: vi.fn(), getCodeSubmissionHistory: vi.fn(),
}))

const wrappers = []
const open = () => {
  const wrapper = mount(StudentProgrammingSubmissionView, { props: { assignmentId: '6' } })
  wrappers.push(wrapper)
  return wrapper
}
beforeEach(() => {
  vi.useFakeTimers()
  vi.resetAllMocks()
  localStorage.clear()
  currentUser.mockReturnValue({ id: 40, role: 'STUDENT' })
  ai.getStudentAiStatus.mockResolvedValue({ configured: true, enabled: true, student_daily_limit: 30 })
  ai.getAiHistory.mockResolvedValue({ items: [] })
  ai.askAi.mockImplementation(async (_m, _id, payload) => ({ id: 1, ...payload, status: 'SUCCEEDED', answer: '逐行解释' }))
  api.getProgrammingProblem.mockResolvedValue({ title: '求和', samples: [], time_limit_ms: 2000, memory_limit_mb: 256 })
  api.getCodeSubmission.mockResolvedValue({ id: 7, version: 1, status: 'AC', passed_case_count: 2, executed_case_count: 2 })
  api.getCodeSubmissionHistory.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 5 })
})
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.useRealTimers()
})

it('忽略无法确定归属的旧草稿和提交 ID', async () => {
  localStorage.setItem('algopeer:programming-draft:6', '// OTHER_STUDENT_PRIVATE_CODE')
  localStorage.setItem('algopeer:programming-submission:6', '999')
  const wrapper = open()
  await flushPromises()
  expect(wrapper.get('textarea').element.value).not.toContain('OTHER_STUDENT_PRIVATE_CODE')
  expect(api.getCodeSubmission).not.toHaveBeenCalled()
})

it('只恢复本人草稿，判题结果由服务端当前版本恢复', async () => {
  localStorage.setItem('algopeer:programming-draft:40:6', '// OWN_DRAFT')
  localStorage.setItem('algopeer:programming-submission:40:6', '999')
  api.getCodeSubmissionHistory.mockResolvedValue({ items: [{ id: 7, version: 1, status: 'AC', is_current: true, submitted_at: '2026-10-13T06:00:00Z' }], total: 1, page: 1 })
  const wrapper = open()
  await flushPromises()
  expect(wrapper.get('textarea').element.value).toBe('// OWN_DRAFT')
  expect(api.getCodeSubmission).toHaveBeenCalledExactlyOnceWith(7)
  expect(wrapper.text()).toContain('通过')
})

it('切换账号不读取上一学生的数据，也不覆盖其草稿', async () => {
  localStorage.setItem('algopeer:programming-draft:40:6', '// A_PRIVATE')
  localStorage.setItem('algopeer:programming-submission:40:6', '7')
  currentUser.mockReturnValue({ id: 42, role: 'STUDENT' })
  const wrapper = open()
  await flushPromises()
  expect(wrapper.get('textarea').element.value).not.toContain('A_PRIVATE')
  expect(api.getCodeSubmission).not.toHaveBeenCalled()
  await wrapper.get('textarea').setValue('// B_DRAFT')
  await vi.advanceTimersByTimeAsync(500)
  expect(localStorage.getItem('algopeer:programming-draft:42:6')).toBe('// B_DRAFT')
  expect(localStorage.getItem('algopeer:programming-draft:40:6')).toBe('// A_PRIVATE')
})

it('新提交后刷新服务端历史，不依赖本地提交 ID', async () => {
  api.submitCode.mockResolvedValue({ submission_id: 7, version: 1, status: 'QUEUED' })
  const wrapper = open()
  await flushPromises()
  await wrapper.get('.submit-button').trigger('click')
  await flushPromises()
  expect(api.getCodeSubmissionHistory).toHaveBeenCalledTimes(2)
  expect(api.getCodeSubmissionHistory).toHaveBeenLastCalledWith('6', 1, 5)
  expect(wrapper.find('.submit-panel .result').text()).toContain('通过')
  expect(localStorage.getItem('algopeer:programming-submission:6')).toBeNull()
})

it('查看旧版不会替换代码，也不会阻止当前版本判题完成后重新提交', async () => {
  localStorage.setItem('algopeer:programming-draft:40:6', '// CURRENT_EDITOR')
  api.getCodeSubmissionHistory.mockResolvedValue({ items: [
    { id: 8, version: 8, status: 'RUNNING', is_current: true, submitted_at: '2026-10-13T06:00:00Z' },
    { id: 1, version: 1, status: 'QUEUED', is_current: false, submitted_at: '2026-10-13T05:00:00Z' },
  ], total: 2, page: 1 })
  let currentPolls = 0
  api.getCodeSubmission.mockImplementation(async (id) => ({
    id, version: id === 8 ? 8 : 1, status: id === 8 ? (++currentPolls === 1 ? 'RUNNING' : 'AC') : 'QUEUED',
    passed_case_count: 2, executed_case_count: 2,
  }))
  const wrapper = open()
  await flushPromises()
  expect(wrapper.get('.submit-button').element.disabled).toBe(true)
  await wrapper.get('button[aria-label="查看第 1 次提交结果"]').trigger('click')
  await flushPromises()
  expect(wrapper.get('textarea').element.value).toBe('// CURRENT_EDITOR')
  await vi.advanceTimersByTimeAsync(2000)
  await flushPromises()
  expect(wrapper.get('.submit-button').element.disabled).toBe(false)
  expect(wrapper.get('textarea').element.value).toBe('// CURRENT_EDITOR')
  expect(wrapper.get('.history-detail').text()).toContain('排队中')
  expect(wrapper.get('.submit-panel .result').text()).toContain('通过')
})

it('提交被截止或状态规则拒绝时给出明确提示，不保存提交记录', async () => {
  api.submitCode.mockRejectedValue(Object.assign(new Error('INVALID_STATE'), { code: 'INVALID_STATE' }))
  const wrapper = open()
  await flushPromises()
  await wrapper.get('.submit-button').trigger('click')
  await flushPromises()
  expect(wrapper.get('[role=alert]').text()).toContain('作业已截止或当前状态不允许提交')
  expect(localStorage.getItem('algopeer:programming-submission:40:6')).toBeNull()
  expect(api.getCodeSubmission).not.toHaveBeenCalled()
})

it('编程页把编辑器选中片段和当前判题提交交给助教', async () => {
  api.getCodeSubmissionHistory.mockResolvedValue({ items: [{ id: 7, version: 1, status: 'AC', is_current: true }], total: 1, page: 1 })
  const w = open(); await flushPromises()
  await w.get('#source-code').setValue('int main() { return 0; }')
  const editor = w.get('#source-code')
  editor.element.setSelectionRange(13, 21); await editor.trigger('select')
  await w.findAll('button').find(b => b.text() === '问助教').trigger('click'); await flushPromises()
  await w.findAll('button').find(b => b.text() === '解释代码').trigger('click'); await flushPromises()
  expect(ai.askAi).toHaveBeenCalledWith('PROGRAMMING', '6', expect.objectContaining({ source_code: 'int main() { return 0; }', selected_code: 'return 0', submission_id: 7 }))
})
