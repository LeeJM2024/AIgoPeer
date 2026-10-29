// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TeacherAssignmentView from './TeacherAssignmentView.vue'
import * as api from '../../api/teacher'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '4' } }),
  RouterLink: { template: '<a><slot /></a>' },
}))
vi.mock('../../api/teacher', () => ({
  getAssignment: vi.fn(), getClassStudents: vi.fn(),
  getAlgorithmRuns: vi.fn(), getProgrammingResults: vi.fn(),
  aggregateReviews: vi.fn(), initializeReviewTasks: vi.fn(),
  publishAssignment: vi.fn(), savePanels: vi.fn(),
}))

const detail = () => ({
  id: 4, title: '跨班评审测试', type: 'FINAL_PROJECT',
  status: 'REVIEWER_GRADING', teacher_weight: 0.6,
  designated_review_weight: 0.4, rubric_items: [],
  classes: [{ id: 11, name: '一班' }, { id: 22, name: '二班' }],
  panels: [
    { reviewer_class_id: 22, target_class_id: 11, reviewer_ids: [6, 7, 8, 9, 10] },
    { reviewer_class_id: 11, target_class_id: 22, reviewer_ids: [1, 2, 3, 4, 5] },
  ],
})
const counts = (wrapper) => wrapper.findAll('.selection-count').map((n) => n.text())
const aggregateButton = (wrapper) => wrapper.findAll('button').find((b) => b.text().includes('汇总评审结果'))

beforeEach(() => {
  vi.resetAllMocks()
  api.getAssignment.mockResolvedValue(detail())
  api.getAlgorithmRuns.mockResolvedValue([])
  api.getClassStudents.mockImplementation(async (id) =>
    (id === 11 ? [1, 2, 3, 4, 5] : [6, 7, 8, 9, 10]).map((id) => ({ id, name: `学生${id}`, student_no: `TEST-${id}` })))
})

describe('教师作业详情', () => {
  it('按评审班回填已保存的五名评审人', async () => {
    const wrapper = mount(TeacherAssignmentView)
    await flushPromises()
    expect(counts(wrapper)).toEqual(['已选择 5 / 5 人', '已选择 5 / 5 人'])
    expect(wrapper.findAll('input[type=checkbox]').every((n) => n.element.checked)).toBe(true)
    wrapper.unmount()
  })

  it('运行记录失败时仍显示已保存人数并允许聚合', async () => {
    api.getAlgorithmRuns.mockRejectedValue(new Error('运行记录暂不可用'))
    const wrapper = mount(TeacherAssignmentView)
    await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('运行记录暂不可用')
    expect(counts(wrapper)).toEqual(['已选择 5 / 5 人', '已选择 5 / 5 人'])
    expect(aggregateButton(wrapper).element.disabled).toBe(false)
    wrapper.unmount()
  })

  it('学生名单尚未返回时，人数已从作业详情回填', async () => {
    api.getClassStudents.mockReturnValue(new Promise(() => {}))
    const wrapper = mount(TeacherAssignmentView)
    await flushPromises()
    expect(counts(wrapper)).toEqual(['已选择 5 / 5 人', '已选择 5 / 5 人'])
    wrapper.unmount()
  })

  it('学生名单失败不覆盖已保存的评审人数', async () => {
    api.getClassStudents.mockRejectedValue(new Error('学生名单暂不可用'))
    const wrapper = mount(TeacherAssignmentView)
    await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('学生名单暂不可用')
    expect(counts(wrapper)).toEqual(['已选择 5 / 5 人', '已选择 5 / 5 人'])
    wrapper.unmount()
  })

  it('成绩发布后保留人数显示并移除聚合入口', async () => {
    api.getAssignment.mockResolvedValue({ ...detail(), status: 'PUBLISHED_RESULT' })
    const wrapper = mount(TeacherAssignmentView)
    await flushPromises()
    expect(counts(wrapper)).toEqual(['已选择 5 / 5 人', '已选择 5 / 5 人'])
    expect(aggregateButton(wrapper)).toBeUndefined()
    wrapper.unmount()
  })

  it.each(['REVIEWER_GRADING', 'AGGREGATING', 'TEACHER_GRADING'])('在 %s 空闲时可聚合，请求中禁用，成功后恢复', async (status) => {
    api.getAssignment.mockResolvedValue({ ...detail(), status })
    let resolve
    api.aggregateReviews.mockReturnValue(new Promise((r) => { resolve = r }))
    const wrapper = mount(TeacherAssignmentView)
    await flushPromises()
    const button = aggregateButton(wrapper)
    expect(button.element.disabled).toBe(false)
    await button.trigger('click')
    expect(api.aggregateReviews).toHaveBeenCalledExactlyOnceWith(4)
    expect(button.element.disabled).toBe(true)
    resolve({ panels: [{ status: 'COMPLETED' }, { status: 'COMPLETED' }] })
    await flushPromises()
    expect(wrapper.get('[role=status]').text()).toContain('评审结果汇总完成')
    expect(aggregateButton(wrapper).element.disabled).toBe(false)
    expect(counts(wrapper)).toEqual(['已选择 5 / 5 人', '已选择 5 / 5 人'])
    wrapper.unmount()
  })

  it('聚合失败后显示错误并允许重试', async () => {
    api.aggregateReviews.mockRejectedValue(new Error('评分尚未到齐'))
    const wrapper = mount(TeacherAssignmentView)
    await flushPromises()
    await aggregateButton(wrapper).trigger('click')
    await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('评分尚未到齐')
    expect(aggregateButton(wrapper).element.disabled).toBe(false)
    wrapper.unmount()
  })
})
