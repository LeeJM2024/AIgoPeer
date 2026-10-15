// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import RegisterView from './RegisterView.vue'
import LoginView from './LoginView.vue'
import { register } from '../api/auth'

vi.mock('../api/auth', () => ({ register: vi.fn(), login: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }), useRouter: () => ({ push: vi.fn() }) }))
const wrappers = []
function open(component = RegisterView) {
  const wrapper = mount(component, { global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } } })
  wrappers.push(wrapper)
  return wrapper
}
async function fill(wrapper, confirmation = ' StudentPassword2026! ') {
  const inputs = wrapper.findAll('input')
  await inputs[0].setValue(' 20260001 ')
  await inputs[1].setValue(' 测试学生 ')
  await inputs[2].setValue(' StudentPassword2026! ')
  await inputs[3].setValue(confirmation)
}
beforeEach(() => vi.resetAllMocks())
afterEach(() => wrappers.splice(0).forEach((wrapper) => wrapper.unmount()))

it('登录页提供学生注册入口', () => {
  expect(open(LoginView).get('a[href="/register"]').text()).toBe('学生注册')
})

it('拒绝密码不一致，不调用注册接口', async () => {
  const wrapper = open()
  await fill(wrapper, 'DifferentPassword2026!')
  await wrapper.get('form').trigger('submit')
  expect(wrapper.get('[role=alert]').text()).toContain('两次输入的密码不一致')
  expect(register).not.toHaveBeenCalled()
})

it('注册去除身份字段空白并保留密码，成功后清空密码且提供登录入口', async () => {
  register.mockResolvedValue({ user: { id: 1, role: 'STUDENT' } })
  const wrapper = open()
  await fill(wrapper)
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(register).toHaveBeenCalledExactlyOnceWith('20260001', '测试学生', ' StudentPassword2026! ')
  expect(wrapper.get('[role=status]').text()).toContain('账号已创建')
  expect(wrapper.text()).toContain('联系任课教师')
  expect(wrapper.get('a[href="/login"]').text()).toBe('前往登录')
  expect(wrapper.find('input[type=password]').exists()).toBe(false)
})

it('重复学号提示可以直接登录，提交后恢复按钮', async () => {
  register.mockRejectedValue(Object.assign(new Error('此学号已注册或已由教师创建，请直接登录。'), { code: 'ACCOUNT_ALREADY_EXISTS' }))
  const wrapper = open()
  await fill(wrapper)
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.get('[role=alert]').text()).toContain('请直接登录')
  expect(wrapper.get('button').element.disabled).toBe(false)
})

it('注册期间禁用表单并阻止重复请求', async () => {
  let finish
  register.mockImplementation(() => new Promise((resolve) => { finish = resolve }))
  const wrapper = open()
  await fill(wrapper)
  await wrapper.get('form').trigger('submit')
  expect(wrapper.get('button').element.disabled).toBe(true)
  expect(wrapper.findAll('input').every((input) => input.element.disabled)).toBe(true)
  await wrapper.get('form').trigger('submit')
  expect(register).toHaveBeenCalledTimes(1)
  finish({ user: { id: 1, role: 'STUDENT' } })
  await flushPromises()
})
