// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import TeacherLearningAnalysisView from './TeacherLearningAnalysisView.vue'
import * as api from '../../api/teacher'
const replace = vi.fn()
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }), useRouter: () => ({ replace }), RouterLink: { template: '<a><slot /></a>' } }))
vi.mock('../../api/teacher', () => ({ getClasses: vi.fn(), getLearningAnalysis: vi.fn() }))
const report = () => ({ assignment_count: 1, code_attempt_count: 4, generated_at: '2026-10-22T00:00:00Z',
  assignments: [{ id: 1, title: '求和', type: 'PROGRAMMING', enrolled_students: 10, submitted_students: 3,
    unsubmitted_students: 7, submission_count: 4, average_attempts: 1.33, passed_students: 1,
    judged_students: 2, current_passed_students: 1, ac_rate: .5, difficulty: .5,
    average_time_ms: 5, peak_memory_kb: 200, pending_count: 1, system_errors: 0, error_counts: { WA: 2 } }],
  topics: [{ id: 1, code: '01', name: '归纳', mastery: null, evidence_count: 0, student_count: 0, assignment_count: 0 }],
  error_counts: { WA: 2 }, definitions: { missing: '未提交不计零分' } })
beforeEach(() => {
  vi.resetAllMocks()
  api.getClasses.mockResolvedValue([{ id: 1, name: '一班', course_term: '秋季' }])
  api.getLearningAnalysis.mockResolvedValue(report())
})
it('准确显示题目、错误、样本量和缺失掌握度', async () => {
  const w = mount(TeacherLearningAnalysisView); await flushPromises()
  expect(w.text()).toContain('学习过程分析')
  expect(w.text()).toContain('50.0%')
  expect(w.text()).toContain('答案错误')
  expect(w.text()).toContain('暂无数据')
  expect(w.text()).toContain('0 个学生—作业样本')
  expect(w.text()).toContain('未提交不计零分')
  await w.get('select').setValue('1'); await w.get('select').trigger('change')
  expect(replace).toHaveBeenCalledWith({ query: { class_id: '1' } })
  w.unmount()
})
it('请求失败不展示旧统计，可重试', async () => {
  api.getLearningAnalysis.mockRejectedValueOnce(new Error('网络错误'))
  const w = mount(TeacherLearningAnalysisView); await flushPromises()
  expect(w.get('[role=alert]').text()).toContain('网络错误')
  expect(w.find('table').exists()).toBe(false)
  await w.findAll('button').find(b => b.text() === '重试').trigger('click'); await flushPromises()
  expect(w.find('table').exists()).toBe(true)
  w.unmount()
})
