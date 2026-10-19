// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import TeacherDashboardView from './TeacherDashboardView.vue'
import { getAssignments, getDashboard } from '../../api/teacher'

vi.mock('../../api/teacher', () => ({ getAssignments: vi.fn(), getDashboard: vi.fn() }))
const wrappers = []
const stats = { active_assignments: 2, awaiting_grading: 0, pending_tasks: 80, open_anomalies: 0 }
function open() {
  const wrapper = mount(TeacherDashboardView, { global: { stubs: {
    RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
  } } })
  wrappers.push(wrapper)
  return wrapper
}
beforeEach(() => vi.resetAllMocks())
afterEach(() => wrappers.splice(0).forEach(wrapper => wrapper.unmount()))

it('保留零值，只为真实阶段的作业生成对应待办', async () => {
  getDashboard.mockResolvedValue(stats)
  getAssignments.mockResolvedValue([
    { id: 1, title: '评审作业', type: 'FINAL_PROJECT', status: 'REVIEWER_GRADING', submission_count: 16 },
    { id: 2, title: '评分作业', type: 'FINAL_PROJECT', status: 'TEACHER_GRADING', submission_count: 4 },
    { id: 3, title: '草稿作业', type: 'PROGRAMMING', status: 'DRAFT', submission_count: 0 },
  ])
  const wrapper = open()
  await flushPromises()
  expect(wrapper.findAll('.metric-strip strong').map(item => item.text())).toEqual(['2', '0', '80', '0'])
  expect(wrapper.findAll('.next-task')).toHaveLength(2)
  expect(wrapper.get('a.next-task[href="/teacher/assignments/1/reviews"]').text()).toContain('评审作业')
  expect(wrapper.get('a.next-task[href="/teacher/assignments/2/grading"]').text()).toContain('评分作业')
  expect(wrapper.find('a.next-task[href*="/3/"]').exists()).toBe(false)
})

it('加载失败不伪装空课程，重试成功后恢复真实页面', async () => {
  getDashboard.mockRejectedValueOnce(new Error('网络异常')).mockResolvedValueOnce(stats)
  getAssignments.mockResolvedValue([])
  const wrapper = open()
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('网络异常')
  expect(wrapper.find('.dashboard-columns').exists()).toBe(false)
  await wrapper.get('[role="alert"] button').trigger('click')
  await flushPromises()
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  expect(wrapper.text()).toContain('还没有作业')
})
