// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import StudentWorkspaceView from './StudentWorkspaceView.vue'
import { getMyAssignments } from '../../api/student/assignments'

vi.mock('../../api/student/assignments', () => ({ getMyAssignments: vi.fn() }))
const wrappers = []
function open() {
  const wrapper = mount(StudentWorkspaceView, { global: { stubs: {
    RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
  } } })
  wrappers.push(wrapper)
  return wrapper
}
beforeEach(() => vi.resetAllMocks())
afterEach(() => wrappers.splice(0).forEach(wrapper => wrapper.unmount()))

it('统计使用真实列表，筛选和搜索不改变总数', async () => {
  getMyAssignments.mockResolvedValue([
    { id: 1, title: '整数求和', type: 'PROGRAMMING', status: 'PUBLISHED', submission: { status: 'AC' } },
    { id: 2, title: '算法微课', type: 'FINAL_PROJECT', status: 'PUBLISHED_RESULT', submission: { status: 'VALID' } },
  ])
  const wrapper = open()
  await flushPromises()
  expect(wrapper.findAll('.student-metrics strong').map(item => item.text())).toEqual(['2 份', '2 份', '1 份'])
  await wrapper.get('[aria-label="按作业类型筛选"]').findAll('button')[1].trigger('click')
  expect(wrapper.findAll('.assignment-card')).toHaveLength(1)
  expect(wrapper.get('.assignment-card').text()).toContain('整数求和')
  await wrapper.get('[aria-label="搜索我的作业"]').setValue('不存在')
  expect(wrapper.text()).toContain('没有找到符合条件的作业')
  await wrapper.get('.empty-state button').trigger('click')
  expect(wrapper.findAll('.assignment-card')).toHaveLength(2)
})

it('错误可重试，空列表提示联系教师加入班级', async () => {
  getMyAssignments.mockRejectedValueOnce(new Error('网络异常')).mockResolvedValueOnce([])
  const wrapper = open()
  await flushPromises()
  expect(wrapper.get('[role=alert]').text()).toContain('网络异常')
  await wrapper.get('.retry-button').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('请联系任课教师加入课程班级')
  expect(wrapper.find('[role=alert]').exists()).toBe(false)
})
