// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TeacherAssignmentView from './TeacherAssignmentView.vue'
import * as api from '../../api/teacher'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '4' } }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: '<a><slot /></a>' },
}))
vi.mock('../../api/teacher', () => ({
  getAssignment: vi.fn(), getClassStudents: vi.fn(),
  getAlgorithmRuns: vi.fn(), getProgrammingResults: vi.fn(),
  aggregateReviews: vi.fn(), initializeReviewTasks: vi.fn(),
  publishAssignment: vi.fn(), getAllocationPreview: vi.fn(),
  closeAssignment: vi.fn(), reopenAssignment: vi.fn(), deleteAssignment: vi.fn(), finishSubmissions: vi.fn(),
  getSubjectiveAnswers: vi.fn(), getEvidence: vi.fn(),
}))
const detail = () => ({
  id: 4, title: '跨班评审测试', type: 'FINAL_PROJECT',
  status: 'PUBLISHED', teacher_weight: .6, designated_review_weight: .4,
  submit_deadline: '2020-01-01', review_deadline: '2030-01-01',
  rubric_items: [], classes: [{ id: 11, name: '一班' }, { id: 22, name: '二班' }],
  panels: [],
})
const preview = () => ({
  snapshot_hash: 'a'.repeat(64), seed: 42, ready: true, blockers: [], total_tasks: 700,
  directions: [
    { reviewer_class_id: 11, reviewer_class_name: '一班', target_class_name: '二班', reviewer_count: 100, submission_count: 40, task_count: 200, min_load: 2, max_load: 2, participants: [] },
    { reviewer_class_id: 22, reviewer_class_name: '二班', target_class_name: '一班', reviewer_count: 40, submission_count: 100, task_count: 500, min_load: 12, max_load: 13, participants: [] },
  ],
})
const button = (wrapper, text) => wrapper.findAll('button').find(b => b.text().includes(text))
beforeEach(() => {
  vi.resetAllMocks()
  window.confirm = vi.fn(() => true)
  api.getAssignment.mockResolvedValue(detail())
  api.getAlgorithmRuns.mockResolvedValue([])
  api.getClassStudents.mockResolvedValue([])
  api.getAllocationPreview.mockResolvedValue(preview())
  api.getSubjectiveAnswers.mockResolvedValue({ total: 0, submitted: 0, items: [] })
})

it.each(['PROOF', 'ALGORITHM_ANALYSIS', 'OPEN_ENDED'])('%s 详情展示作答情况，没有评分或评审入口', async (type) => {
  api.getAssignment.mockResolvedValue({ ...detail(), type, statement: '请作答。', review_deadline: null })
  const wrapper = mount(TeacherAssignmentView)
  await flushPromises()
  expect(api.getAllocationPreview).not.toHaveBeenCalled()
  expect(api.getAlgorithmRuns).not.toHaveBeenCalled()
  expect(api.getSubjectiveAnswers).toHaveBeenCalledWith(4, 1)
  expect(wrapper.text()).toContain('学生作答情况')
  expect(wrapper.text()).not.toContain('进入评分工作台')
  expect(wrapper.text()).not.toContain('跨班随机评审分配')
  expect(wrapper.text()).not.toContain('评分量表')
  wrapper.unmount()
})
describe('跨班分配确认', () => {
  it('提交截止前也能开始评审，并继续接收提交', async () => {
    api.getAssignment.mockResolvedValue({ ...detail(), submit_deadline: '2029-01-01', review_deadline: '2030-01-01' })
    api.initializeReviewTasks.mockResolvedValue({ panels: [{ task_count: 700 }] })
    const w = mount(TeacherAssignmentView); await flushPromises()
    await w.get('input[type=checkbox]').setValue(true)
    expect(button(w, '确认并生成').element.disabled).toBe(false)
    expect(w.text()).toContain('生成任务不结束提交')
    await button(w, '确认并生成').trigger('click'); await flushPromises()
    expect(api.initializeReviewTasks).toHaveBeenCalledWith(4, 'a'.repeat(64))
    w.unmount()
  })
  it('评审进行中可补充分配，并先结束提交再汇总', async () => {
    api.getAssignment.mockResolvedValue({ ...detail(), status: 'REVIEWER_GRADING', submit_deadline: '2029-01-01' })
    api.getAllocationPreview.mockResolvedValue({ ...preview(), existing_task_count: 100, new_task_count: 20 })
    const w = mount(TeacherAssignmentView); await flushPromises()
    await w.get('input[type=checkbox]').setValue(true)
    expect(button(w, '确认并生成').element.disabled).toBe(false)
    expect(button(w, '汇总评审').element.disabled).toBe(true)
    expect(button(w, '结束提交')).toBeDefined()
    w.unmount()
  })
  it('关闭后显示恢复入口并禁用业务操作', async () => {
    api.getAssignment.mockResolvedValue({ ...detail(), closed_at: '2026-10-28T00:00:00Z' })
    const w = mount(TeacherAssignmentView); await flushPromises()
    expect(button(w, '恢复作业')).toBeDefined()
    expect(button(w, '确认并生成')).toBeUndefined()
    await button(w, '恢复作业').trigger('click'); await flushPromises()
    expect(api.reopenAssignment).toHaveBeenCalledWith(4)
    w.unmount()
  })
  it('展示实际两班人数和不同任务配额，不再提供固定五人选择', async () => {
    const wrapper = mount(TeacherAssignmentView)
    await flushPromises()
    expect(wrapper.text()).toContain('每人 2～2 份')
    expect(wrapper.text()).toContain('每人 12～13 份')
    expect(wrapper.text()).not.toContain('保存评审组')
    expect(button(wrapper, '确认并生成').element.disabled).toBe(true)
    await wrapper.get('input[type=checkbox]').setValue(true)
    api.initializeReviewTasks.mockResolvedValue({ panels: [{ task_count: 700 }] })
    await button(wrapper, '确认并生成').trigger('click')
    await flushPromises()
    expect(api.initializeReviewTasks).toHaveBeenCalledWith(4, 'a'.repeat(64))
    expect(wrapper.text()).toContain('共 700 条')
    expect(wrapper.get('input[type=checkbox]').element.checked).toBe(false)
    wrapper.unmount()
  })
  it('预览更新后必须重新确认', async () => {
    const wrapper = mount(TeacherAssignmentView)
    await flushPromises()
    await wrapper.get('input[type=checkbox]').setValue(true)
    await button(wrapper, '刷新名单').trigger('click')
    await flushPromises()
    expect(button(wrapper, '确认并生成').element.disabled).toBe(true)
    wrapper.unmount()
  })
  it('过期预览失败后禁用分配，保留重试入口', async () => {
    api.initializeReviewTasks.mockRejectedValue(new Error('名单已变化，请刷新'))
    const wrapper = mount(TeacherAssignmentView)
    await flushPromises()
    await wrapper.get('input[type=checkbox]').setValue(true)
    await button(wrapper, '确认并生成').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('名单已变化')
    expect(button(wrapper, '确认并生成').element.disabled).toBe(true)
    expect(button(wrapper, '刷新名单')).toBeDefined()
    wrapper.unmount()
  })
  it('不可行名单不允许勾选确认', async () => {
    api.getAllocationPreview.mockResolvedValue({ ...preview(), ready: false, blockers: ['ALLOCATION_INFEASIBLE'] })
    const wrapper = mount(TeacherAssignmentView)
    await flushPromises()
    expect(wrapper.get('input[type=checkbox]').element.disabled).toBe(true)
    expect(wrapper.text()).toContain('当前人数无法')
    wrapper.unmount()
  })
  it('草稿不需配置固定评委即可发布', async () => {
    api.getAssignment.mockResolvedValue({ ...detail(), status: 'DRAFT' })
    const wrapper = mount(TeacherAssignmentView)
    await flushPromises()
    expect(button(wrapper, '确认并发布').element.disabled).toBe(false)
    wrapper.unmount()
  })
  it.each(['REVIEWER_GRADING', 'AGGREGATING', 'TEACHER_GRADING'])('%s 可汇总并显示失败', async status => {
    api.getAssignment.mockResolvedValue({ ...detail(), status })
    api.aggregateReviews.mockRejectedValue(new Error('评分尚未到齐'))
    const wrapper = mount(TeacherAssignmentView)
    await flushPromises()
    await button(wrapper, '汇总评审').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('评分尚未到齐')
    expect(button(wrapper, '汇总评审').element.disabled).toBe(false)
    wrapper.unmount()
  })
})
