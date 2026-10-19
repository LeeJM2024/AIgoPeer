// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import LoginView from './LoginView.vue'
import { login } from '../api/auth'

const { push } = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock('../api/auth', () => ({ login: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }), useRouter: () => ({ push }) }))
let wrapper
beforeEach(() => {
  vi.resetAllMocks()
  wrapper = mount(LoginView, { global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } } })
})
afterEach(() => wrapper.unmount())

it('密码可显示和隐藏，不提交表单也不改变内容', async () => {
  await wrapper.get('input[autocomplete="current-password"]').setValue('LocalTestPassword!')
  await wrapper.get('[aria-label="显示密码"]').trigger('click')
  expect(wrapper.get('input[autocomplete="current-password"]').attributes('type')).toBe('text')
  expect(wrapper.get('[aria-label="隐藏密码"]').attributes('aria-pressed')).toBe('true')
  await wrapper.get('[aria-label="隐藏密码"]').trigger('click')
  expect(wrapper.get('input[type="password"]').element.value).toBe('LocalTestPassword!')
  expect(login).not.toHaveBeenCalled()
})

it('登录中阻止重复请求，成功仍按角色进入工作台', async () => {
  let finish
  login.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  await wrapper.get('input[autocomplete="username"]').setValue(' T001 ')
  await wrapper.get('input[type="password"]').setValue('LocalTestPassword!')
  await wrapper.get('form').trigger('submit')
  await wrapper.get('form').trigger('submit')
  expect(login).toHaveBeenCalledExactlyOnceWith('T001', 'LocalTestPassword!')
  expect(wrapper.get('button[type="submit"], .auth-form > .button').element.disabled).toBe(true)
  finish({ role: 'TEACHER' })
  await flushPromises()
  expect(push).toHaveBeenCalledWith('/teacher')
})

it('登录错误保留输入并显示可读提示', async () => {
  login.mockRejectedValue(new Error('INVALID_CREDENTIALS'))
  await wrapper.get('input[autocomplete="username"]').setValue('wrong')
  await wrapper.get('input[type="password"]').setValue('LocalTestPassword!')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toBe('账号或密码不正确。')
  expect(wrapper.get('input[autocomplete="username"]').element.value).toBe('wrong')
})
