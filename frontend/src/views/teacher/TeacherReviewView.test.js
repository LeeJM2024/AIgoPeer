// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TeacherReviewView from './TeacherReviewView.vue'
import * as api from '../../api/teacher'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '4' } }),
  RouterLink: { template: '<a><slot /></a>' },
}))
vi.mock('../../api/teacher', () => ({
  getAssignment: vi.fn(), getAnomalies: vi.fn(), getReviewProgress: vi.fn(),
  extendReviewDeadline: vi.fn(), resolveAnomaly: vi.fn(), replaceReviewTask: vi.fn(),
}))
const button = (wrapper, text) => wrapper.findAll('button').find(b => b.text().includes(text))
beforeEach(() => {
  vi.resetAllMocks()
  api.getAssignment.mockResolvedValue({ title: '证明题', status: 'REVIEWER_GRADING', review_deadline: '2030-01-01', rubric_items: [] })
  api.getAnomalies.mockResolvedValue([])
  api.getReviewProgress.mockResolvedValue([{
    panel_id: 1, reviewer_id: 8, reviewer_name: '学生', target_class_name: '一班',
    task_count: 5, completed_count: 4,
    missing_tasks: [{ task_id: 20, anonymous_token: 'WORK-20', status: 'PENDING' }],
  }])
})
describe('教师替补评审', () => {
  it('原因确认后才替换，并刷新真实进度', async () => {
    const wrapper = mount(TeacherReviewView)
    await flushPromises()
    await button(wrapper, '安排替补').trigger('click')
    expect(button(wrapper, '确认并安排').element.disabled).toBe(true)
    const form = wrapper.get('form[aria-labelledby=replacement-heading]')
    await form.get('textarea').setValue('原评委请假，安排替补')
    await form.trigger('submit')
    await flushPromises()
    expect(api.replaceReviewTask).toHaveBeenCalledWith(4, 20, '原评委请假，安排替补')
    expect(api.getReviewProgress).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[role=status]').text()).toContain('原任务已停用并留档')
    expect(wrapper.find('form[aria-labelledby=replacement-heading]').exists()).toBe(false)
    wrapper.unmount()
  })
  it('失败保留原因与重试入口', async () => {
    api.replaceReviewTask.mockRejectedValue(new Error('当前没有符合约束的替补人选'))
    const wrapper = mount(TeacherReviewView)
    await flushPromises()
    await button(wrapper, '安排替补').trigger('click')
    const form = wrapper.get('form[aria-labelledby=replacement-heading]')
    await form.get('textarea').setValue('原评委请假')
    await form.trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('没有符合约束')
    expect(form.get('textarea').element.value).toBe('原评委请假')
    expect(button(wrapper, '确认并安排').element.disabled).toBe(false)
    wrapper.unmount()
  })
  it('评审截止后不提供替补操作', async () => {
    api.getAssignment.mockResolvedValue({ status: 'REVIEWER_GRADING', review_deadline: '2020-01-01' })
    const wrapper = mount(TeacherReviewView)
    await flushPromises()
    expect(button(wrapper, '安排替补')).toBeUndefined()
    wrapper.unmount()
  })
})

describe('异常复核说明选填', () => {
  it.each([
    ['LOW', 'DISMISSED', '驳回异常'],
    ['LOW', 'CONFIRMED', '确认异常'],
    ['MEDIUM', 'DISMISSED', '驳回异常'],
    ['MEDIUM', 'CONFIRMED', '确认异常'],
  ])('%s 风险留空说明可以 %s', async (riskLevel, status, label) => {
    const anomaly={id:7,status:'OPEN',risk_level:riskLevel,author_name:'演示学生',student_no:'D101',anonymous_token:'DEMO',evidence_json:{}}
    api.getAnomalies.mockResolvedValueOnce([anomaly]).mockResolvedValue([{...anomaly,status}])
    const wrapper=mount(TeacherReviewView,{global:{stubs:{ReviewEvidence:true}}})
    await flushPromises()
    expect(wrapper.text()).toContain('复核说明（选填）')
    await button(wrapper,label).trigger('click')
    await flushPromises()
    expect(api.resolveAnomaly).toHaveBeenCalledWith(7,{status,note:''})
    expect(wrapper.get('.review-conclusion').text()).toContain('未填写复核说明')
    expect(wrapper.get('.review-conclusion').text()).not.toContain('成绩已发布')
    wrapper.unmount()
  })
})
