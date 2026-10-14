// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import StudentProjectSubmissionView from './StudentProjectSubmissionView.vue'
import * as api from '../../api/student/projectSubmissions'

vi.mock('vue-router', () => ({ RouterLink: { template: '<a><slot /></a>' } }))
vi.mock('../../api/student/projectSubmissions', () => ({
  getAssignmentTopics: vi.fn(), getCurrentProjectSubmission: vi.fn(),
  getMaterialCheck: vi.fn(), claimTopic: vi.fn(), submitProject: vi.fn(),
  getProjectSubmissionHistory: vi.fn(),
}))
const wrappers = []
const current = { id: 71, version: 1, status: 'VALID', submitted_at: '2026-10-14T05:00:00Z' }
const view = (submission = current) => ({
  assignment_id: 1, title: '期末作业', status: 'PUBLISHED',
  submit_deadline: '2026-10-15T00:00:00Z', can_submit: true, submission,
})
const check = (status = 'VALID', missing = []) => ({ status, missing_items: missing, warnings: [] })
const button = (wrapper, label) => wrapper.findAll('button').find((b) => b.text().includes(label))
async function open() {
  const w = mount(StudentProjectSubmissionView, { props: { assignmentId: '1' } })
  wrappers.push(w)
  await flushPromises()
  return w
}
async function upload(w) {
  const file = new File(['test archive'], 'TEST_学生_89.zip', { type: 'application/zip' })
  const input = w.get('input[type=file]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
  await button(w, '上传并检查').trigger('click')
  await flushPromises()
}
beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-14T06:00:00Z'))
  vi.resetAllMocks()
  api.getAssignmentTopics.mockResolvedValue({ topics: [], claim: { id: 1, topic: { code: '89', name: '动态规划' } } })
  api.getCurrentProjectSubmission.mockResolvedValue(view())
  api.getMaterialCheck.mockResolvedValue(check())
  api.getProjectSubmissionHistory.mockResolvedValue({ items: [], total: 0, page: 1 })
})
afterEach(() => {
  wrappers.splice(0).forEach((w) => w.unmount())
  vi.useRealTimers()
})

it('重新进入时从服务端恢复当前版本与缺失材料，不依赖本地缓存', async () => {
  api.getMaterialCheck.mockResolvedValue(check('INVALID', ['VIDEO', 'README']))
  const w = await open()
  expect(api.getCurrentProjectSubmission).toHaveBeenCalledWith(1)
  expect(api.getMaterialCheck).toHaveBeenCalledWith(71)
  expect(w.text()).toContain('当前提交：第 1 版')
  expect(w.text()).toContain('VIDEO、README')
})

it('截止后恢复结果，上传控件禁用，保留刷新入口', async () => {
  api.getCurrentProjectSubmission.mockResolvedValue({ ...view(), submit_deadline: '2026-10-14T06:00:00Z', can_submit: false })
  const w = await open()
  expect(w.text()).toContain('作业已截止')
  expect(w.get('.upload-fields').element.disabled).toBe(true)
  expect(button(w, '上传并检查').element.disabled).toBe(true)
  expect(button(w, '刷新提交状态').element.disabled).toBe(false)
  expect(w.text()).toContain('材料检查结果：VALID')
})

it('页面停留至截止时自动禁用上传', async () => {
  api.getCurrentProjectSubmission.mockResolvedValue({ ...view(), submit_deadline: '2026-10-14T06:00:02Z' })
  const w = await open()
  expect(button(w, '上传并检查').element.disabled).toBe(false)
  await vi.advanceTimersByTimeAsync(2000)
  expect(button(w, '上传并检查').element.disabled).toBe(true)
})

it('后台 PENDING 继续轮询直到完成', async () => {
  api.getMaterialCheck.mockResolvedValueOnce(check('PENDING')).mockResolvedValue(check())
  const w = await open()
  expect(w.text()).toContain('材料检查结果：PENDING')
  await vi.advanceTimersByTimeAsync(2000)
  expect(w.text()).toContain('材料检查结果：VALID')
  await vi.advanceTimersByTimeAsync(10000)
  expect(api.getMaterialCheck).toHaveBeenCalledTimes(2)
})

it('轮询上限有停止提示，手动刷新可继续并读取服务端最新版本', async () => {
  api.getMaterialCheck.mockResolvedValue(check('PENDING'))
  const w = await open()
  await vi.advanceTimersByTimeAsync(40000)
  expect(w.text()).toContain('自动刷新已停止')
  expect(api.getMaterialCheck).toHaveBeenCalledTimes(21)
  await vi.advanceTimersByTimeAsync(6000)
  expect(api.getMaterialCheck).toHaveBeenCalledTimes(21)
  api.getCurrentProjectSubmission.mockResolvedValue(view({ ...current, id: 72, version: 2 }))
  api.getMaterialCheck.mockResolvedValue(check())
  await button(w, '刷新提交状态').trigger('click')
  await flushPromises()
  expect(w.text()).toContain('当前提交：第 2 版')
  expect(w.text()).toContain('材料检查结果：VALID')
  expect(w.text()).not.toContain('自动刷新已停止')
  expect(api.getMaterialCheck).toHaveBeenLastCalledWith(72)
})

it('检查读取失败保留当前版本，刷新后恢复', async () => {
  api.getMaterialCheck.mockRejectedValueOnce(new Error('网络中断')).mockResolvedValue(check())
  const w = await open()
  expect(w.text()).toContain('当前提交：第 1 版')
  expect(w.text()).toContain('网络中断')
  await button(w, '刷新提交状态').trigger('click')
  await flushPromises()
  expect(w.text()).toContain('材料检查结果：VALID')
  expect(w.text()).not.toContain('网络中断')
})

it('重传后旧检查响应不能覆盖新版本结果', async () => {
  let resolveOld
  api.getMaterialCheck.mockImplementation((id) => id === 71
    ? new Promise((resolve) => { resolveOld = resolve }) : Promise.resolve(check('INVALID', ['VIDEO'])))
  api.submitProject.mockResolvedValue({ submission_id: 72, version: 2, material_check_status: 'PENDING' })
  const w = await open()
  await upload(w)
  resolveOld(check())
  await flushPromises()
  expect(w.text()).toContain('当前提交：第 2 版')
  expect(w.text()).toContain('材料检查结果：INVALID')
  expect(w.text()).toContain('缺失项：VIDEO')
})

it('上传途中截止被后端拒绝时保留旧版本并刷新可上传状态', async () => {
  api.submitProject.mockRejectedValue(Object.assign(new Error('INVALID_STATE'), { code: 'INVALID_STATE' }))
  const w = await open()
  api.getCurrentProjectSubmission.mockResolvedValue({ ...view(), can_submit: false })
  await upload(w)
  expect(w.text()).toContain('本次未提交成功，已有版本保持不变')
  expect(w.text()).toContain('当前提交：第 1 版')
  expect(button(w, '上传并检查').element.disabled).toBe(true)
})

it('初次加载失败不展示上传表单，重试后显示无提交状态', async () => {
  api.getCurrentProjectSubmission.mockRejectedValueOnce(new Error('读取失败')).mockResolvedValue(view(null))
  const w = await open()
  expect(w.text()).toContain('读取失败')
  expect(w.find('input[type=file]').exists()).toBe(false)
  await button(w, '重试加载作业').trigger('click')
  await flushPromises()
  expect(w.text()).toContain('当前没有已提交的作业包')
  expect(api.getMaterialCheck).not.toHaveBeenCalled()
})

it('页面离开后停止后台轮询', async () => {
  api.getMaterialCheck.mockResolvedValue(check('PENDING'))
  const w = await open()
  w.unmount()
  wrappers.splice(wrappers.indexOf(w), 1)
  await vi.advanceTimersByTimeAsync(5000)
  expect(api.getMaterialCheck).toHaveBeenCalledTimes(1)
})

it('查看旧版不替换当前版本或表单，当前检查继续完成', async () => {
  api.getCurrentProjectSubmission.mockResolvedValue(view({ ...current, version: 2, status: 'PENDING' }))
  api.getProjectSubmissionHistory.mockResolvedValue({ items: [
    { id: 71, version: 2, is_current: true, material_check_status: 'PENDING', submitted_at: current.submitted_at },
    { id: 70, version: 1, is_current: false, material_check_status: 'INVALID', submitted_at: current.submitted_at },
  ], total: 2, page: 1 })
  let polls = 0
  api.getMaterialCheck.mockImplementation(async (id) => id === 70 ? check('INVALID', ['VIDEO'])
    : check(++polls === 1 ? 'PENDING' : 'VALID'))
  const w = await open()
  await w.get('input[placeholder="slides/lesson.pptx"]').setValue('CURRENT_SLIDES.pptx')
  await w.get('button[aria-label="查看第 1 版材料检查"]').trigger('click')
  await flushPromises()
  await vi.advanceTimersByTimeAsync(2000)
  expect(w.get('.check-result').text()).toContain('当前提交：第 2 版')
  expect(w.get('.check-result').text()).toContain('材料检查结果：VALID')
  expect(w.get('.history-detail').text()).toContain('缺失项：VIDEO')
  expect(w.get('input[placeholder="slides/lesson.pptx"]').element.value).toBe('CURRENT_SLIDES.pptx')
  expect(api.getMaterialCheck.mock.calls.filter(([id]) => id === 70)).toHaveLength(1)
})

it('新上传触发历史第一页刷新', async () => {
  api.submitProject.mockResolvedValue({ submission_id: 72, version: 2, material_check_status: 'PENDING' })
  const w = await open()
  await upload(w)
  expect(api.getProjectSubmissionHistory).toHaveBeenCalledTimes(2)
  expect(api.getProjectSubmissionHistory).toHaveBeenLastCalledWith(1, 1, 5)
})
