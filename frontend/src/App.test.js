// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'
import App from './App.vue'
import { currentUser } from './api/auth'
import { getReviewEligibility } from './api/reviewer'

vi.mock('./api/auth', () => ({ currentUser: vi.fn(), logout: vi.fn() }))
vi.mock('./api/reviewer', () => ({ getReviewEligibility: vi.fn() }))
const wrappers = []
async function open(path) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/:pathMatch(.*)*', component: { template: '<h1>课程内容</h1>' } }
    ]
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [router] } })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}
beforeEach(() => vi.resetAllMocks())
afterEach(() => wrappers.splice(0).forEach((wrapper) => wrapper.unmount()))

it.each([
  ['TEACHER', '/teacher'],
  ['STUDENT', '/student'],
  ['STUDENT', '/reviewer/tasks']
])('%s 的 %s 页面统一使用校院标识且不遗留旧品牌文字', async (role, path) => {
  currentUser.mockReturnValue({ role, name: '演示用户' })
  getReviewEligibility.mockResolvedValue({ has_tasks: true })
  const wrapper = await open(path)
  const image = wrapper.get('.brand-lockup img')
  expect(image.attributes('src')).toContain('hust-cse-logo.png')
  expect(image.attributes('alt')).toBe('华中科技大学 网络空间安全学院')
  expect(wrapper.get('.brand-lockup').attributes('href')).toBe(role === 'TEACHER' ? '/teacher' : '/student')
  expect(wrapper.text()).not.toContain('AlgoPeer')
  expect(wrapper.get('.workspace-footer').text()).toContain('网络空间安全学院')
})

it('教师导航保留五个实际入口，不请求学生评审资格', async () => {
  currentUser.mockReturnValue({ role: 'TEACHER', name: '演示教师' })
  const wrapper = await open('/teacher')
  expect(wrapper.get('nav').attributes('aria-label')).toBe('教师端主导航')
  expect(wrapper.findAll('nav a')).toHaveLength(5)
  expect(getReviewEligibility).not.toHaveBeenCalled()
  expect(wrapper.get('[aria-label="退出登录"]').exists()).toBe(true)
})

it.each([true, false])(
  '学生评审入口与服务端 has_tasks=%s 一致',
  async (hasTasks) => {
    currentUser.mockReturnValue({ role: 'STUDENT', name: '演示学生' })
    getReviewEligibility.mockResolvedValue({ has_tasks: hasTasks })
    const wrapper = await open('/student')
    expect(wrapper.find('a[href="/reviewer/tasks"]').exists()).toBe(hasTasks)
    expect(wrapper.find('a[href="/teacher/assignments"]').exists()).toBe(false)
  }
)

it('资格读取失败时不凭空展示评审入口', async () => {
  currentUser.mockReturnValue({ role: 'STUDENT', name: '演示学生' })
  getReviewEligibility.mockRejectedValue(new Error('离线'))
  const wrapper = await open('/student')
  expect(wrapper.find('a[href="/reviewer/tasks"]').exists()).toBe(false)
})
