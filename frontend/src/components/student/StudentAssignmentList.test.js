// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import StudentAssignmentList from './StudentAssignmentList.vue'

afterEach(() => vi.useRealTimers())

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
