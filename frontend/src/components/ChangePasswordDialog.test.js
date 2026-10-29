// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import ChangePasswordDialog from './ChangePasswordDialog.vue'
import { changePassword } from '../api/auth'

vi.mock('../api/auth', () => ({ changePassword: vi.fn() }))
let wrapper
beforeEach(() => {
  vi.resetAllMocks()
  HTMLDialogElement.prototype.showModal = function () { this.open = true }
  HTMLDialogElement.prototype.close = function () { this.open = false }
  wrapper = mount(ChangePasswordDialog, { global: { stubs: { Teleport: true } } })
})
afterEach(() => wrapper.unmount())
async function fill(next = 'NewPassword2026!', confirm = next) {
  await wrapper.get('#account-current-password').setValue('OriginalPassword2026!')
  await wrapper.get('#account-new-password').setValue(next)
  await wrapper.get('#account-confirm-password').setValue(confirm)
}

it('密码确认失败或复用当前密码时不调用接口', async () => {
  await fill('NewPassword2026!', 'DifferentPassword!')
  await wrapper.get('form').trigger('submit')
  expect(wrapper.get('#confirm-password-error').text()).toContain('不一致')
  await fill('OriginalPassword2026!')
  await wrapper.get('form').trigger('submit')
  expect(wrapper.get('#new-password-error').text()).toContain('不能与当前密码相同')
  expect(changePassword).not.toHaveBeenCalled()
})

it('保存期间禁用表单并阻止重复提交，成功后清空密码', async () => {
  let finish
  changePassword.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  await fill(' NewPassword2026! ')
  await wrapper.get('form').trigger('submit')
  await wrapper.get('form').trigger('submit')
  expect(changePassword).toHaveBeenCalledExactlyOnceWith('OriginalPassword2026!', ' NewPassword2026! ', ' NewPassword2026! ')
  expect(wrapper.findAll('input').every(input => input.element.disabled)).toBe(true)
  await wrapper.get('dialog').trigger('cancel')
  expect(wrapper.emitted('close')).toBeUndefined()
  finish({ changed: true })
  await flushPromises()
  expect(wrapper.text()).toContain('密码已修改')
  expect(wrapper.find('input').exists()).toBe(false)
  await wrapper.get('.password-done').trigger('click')
  expect(wrapper.emitted('close')).toHaveLength(1)
})

it('当前密码错误显示在对应字段旁并保留输入', async () => {
  changePassword.mockRejectedValue(Object.assign(new Error('当前密码不正确，请重新输入。'), { code: 'CURRENT_PASSWORD_INCORRECT' }))
  await fill()
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.get('#current-password-error').text()).toContain('当前密码不正确')
  expect(wrapper.get('#account-new-password').element.value).toBe('NewPassword2026!')
})

it('取消和 Escape 均关闭窗口', async () => {
  await wrapper.get('dialog').trigger('cancel')
  expect(wrapper.emitted('close')).toHaveLength(1)
})
