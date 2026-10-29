// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import SubjectiveAnswers from './SubjectiveAnswers.vue'
import { getEvidence, getSubjectiveAnswers } from '../../api/teacher'

vi.mock('../../api/teacher', () => ({ getEvidence: vi.fn(), getSubjectiveAnswers: vi.fn() }))

it('展示作答人数、未提交学生与答案历史，不提供评分操作', async () => {
  getSubjectiveAnswers.mockResolvedValue({ total: 2, submitted: 1, items: [
    { student_id: 1, name: '学生甲', student_no: 'S001', class_name: '一班', submission_id: 9, version: 2,
      submitted_at: '2026-10-29T00:00:00Z', versions: [
        { id: 9, version: 2, submitted_at: '2026-10-29T00:00:00Z' },
        { id: 8, version: 1, submitted_at: '2026-10-28T00:00:00Z' },
      ] },
    { student_id: 2, name: '学生乙', student_no: 'S002', class_name: '一班', versions: [] },
  ] })
  getEvidence.mockResolvedValueOnce({ answer: '<script>最新答案</script>' }).mockResolvedValueOnce({ answer: '旧版答案' })
  const wrapper = mount(SubjectiveAnswers, { props: { assignmentId: 4 } })
  await flushPromises()
  expect(wrapper.text()).toContain('1 人已提交 · 1 人未提交 · 共 2 人')
  expect(wrapper.text()).toContain('已完成 · v2')
  await wrapper.findAll('button').find(b => b.text() === '查看答案').trigger('click')
  await flushPromises()
  expect(getEvidence).toHaveBeenLastCalledWith(9)
  expect(wrapper.get('pre').text()).toBe('<script>最新答案</script>')
  expect(wrapper.find('script').exists()).toBe(false)
  await wrapper.findAll('button').find(b => b.text().startsWith('v1')).trigger('click')
  await flushPromises()
  expect(getEvidence).toHaveBeenLastCalledWith(8)
  expect(wrapper.get('pre').text()).toBe('旧版答案')
  expect(wrapper.findAll('input[type=number]')).toHaveLength(0)
  wrapper.unmount()
})
