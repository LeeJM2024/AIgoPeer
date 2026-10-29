// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import StudentAssignmentList from './StudentAssignmentList.vue'

afterEach(() => vi.useRealTimers())

it('作业标题中的脚本与 HTML 作为文字呈现', () => {
  const title = '<img src=x onerror="alert(1)"><script>alert(1)</script>{{7*7}}'
  const wrapper = mount(StudentAssignmentList, {
    props: { assignments: [{ id: 1, title, type: 'PROGRAMMING', status: 'PUBLISHED', submit_deadline: '2030-01-01T00:00:00Z' }] },
    global: { stubs: { AssignmentArtwork: true, RouterLink: { template: '<a><slot /></a>' } } },
  })
  expect(wrapper.get('h2').text()).toBe(title)
  expect(wrapper.find('h2 img').exists()).toBe(false)
  expect(wrapper.find('h2 script').exists()).toBe(false)
  wrapper.unmount()
})

it('区分进行中和已截止的编程作业，并保留查看结果入口', () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-13T06:00:00Z'))
  const wrapper = mount(StudentAssignmentList, {
    props: { assignments: [
      { id: 1, title: '进行中作业', type: 'PROGRAMMING', status: 'PUBLISHED', submit_deadline: '2026-10-14T00:00:00Z' },
      { id: 2, title: '已截止作业', type: 'PROGRAMMING', status: 'PUBLISHED', submit_deadline: '2026-10-13T06:00:00Z' },
    ] },
    global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } },
  })
  const cards = wrapper.findAll('.assignment-card')
  expect(cards[0].get('.status-badge').text()).toBe('进行中')
  expect(cards[1].get('.status-badge').text()).toBe('已截止')
  expect(cards[1].get('a').text()).toBe('查看题目与结果')
  expect(cards[1].get('a').attributes('href')).toBe('/student/assignments/2/programming-submission')
  wrapper.unmount()
})

it('期末截止后显示查看提交入口，成绩发布后保留查分入口', () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-14T06:00:00Z'))
  const wrapper = mount(StudentAssignmentList, {
    props: { assignments: [
      { id: 1, title: '期末截止', type: 'FINAL_PROJECT', status: 'PUBLISHED', submit_deadline: '2026-10-14T00:00:00Z' },
      { id: 2, title: '成绩发布', type: 'FINAL_PROJECT', status: 'PUBLISHED_RESULT', submit_deadline: '2026-10-14T00:00:00Z' },
    ] },
    global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } },
  })
  const cards = wrapper.findAll('.assignment-card')
  expect(cards[0].get('a').text()).toBe('查看提交与材料检查')
  expect(cards[1].get('.status-badge').text()).toBe('成绩已发布')
  expect(cards[1].get('a').text()).toBe('查看最终成绩')
  wrapper.unmount()
})
