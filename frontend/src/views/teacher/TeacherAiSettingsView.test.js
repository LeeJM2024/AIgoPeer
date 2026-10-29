// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import TeacherAiSettingsView from './TeacherAiSettingsView.vue'
import { deleteAiVideoSettings, getAiVideoSettings, saveAiVideoSettings, testAiVideoSettings } from '../../api/teacher'

vi.mock('../../api/teacher', () => ({ getAiVideoSettings: vi.fn(), saveAiVideoSettings: vi.fn(), testAiVideoSettings: vi.fn(), deleteAiVideoSettings: vi.fn() }))
const config = { configured: false, enabled: false, provider: 'qwen', base_url: 'https://example.com/v1', model: 'qwen3.5-omni-flash' }
const options = { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } }
beforeEach(() => { vi.resetAllMocks(); getAiVideoSettings.mockResolvedValue({ ...config }) })
afterEach(() => { vi.useRealTimers() })

it('配置请求未返回时，先展示整个界面并禁用保存', async () => {
  let resolve
  getAiVideoSettings.mockReturnValue(new Promise(done => { resolve = done }))
  const wrapper = mount(TeacherAiSettingsView, options)
  expect(wrapper.text()).toContain('从视频到可回看的证据')
  expect(wrapper.find('#ai-provider').exists()).toBe(true)
  expect(wrapper.get('fieldset').element.disabled).toBe(true)
  expect(wrapper.get('button[type=submit]').element.disabled).toBe(true)
  resolve(config); await flushPromises()
  expect(wrapper.get('fieldset').element.disabled).toBe(false)
  wrapper.unmount()
})

it('读取配置八秒超时后可重试，不把默认值作为已保存配置', async () => {
  vi.useFakeTimers()
  getAiVideoSettings.mockImplementationOnce(({ signal }) => new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))))
  const wrapper = mount(TeacherAiSettingsView, options)
  await vi.advanceTimersByTimeAsync(8000); await flushPromises()
  expect(wrapper.get('[role=alert]').text()).toContain('读取配置超时')
  expect(wrapper.get('fieldset').element.disabled).toBe(true)
  await wrapper.findAll('button').find(b => b.text() === '重新加载').trigger('click'); await flushPromises()
  expect(wrapper.get('fieldset').element.disabled).toBe(false)
  expect(wrapper.text()).not.toContain('读取配置超时')
  wrapper.unmount()
})

it('教师填写自己的密钥，保存成功后输入框清空', async () => {
  saveAiVideoSettings.mockResolvedValue({ ...config, configured: true, enabled: true })
  const wrapper = mount(TeacherAiSettingsView, options)
  await flushPromises()
  expect(wrapper.get('button[type=submit]').attributes('disabled')).toBeDefined()
  await wrapper.get('#ai-key').setValue('teacher-key')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(saveAiVideoSettings).toHaveBeenCalledWith(expect.objectContaining({ api_key: 'teacher-key', enabled: true }))
  expect(wrapper.get('#ai-key').element.value).toBe('')
  expect(wrapper.text()).toContain('配置已保存')
  expect(wrapper.text()).not.toContain('teacher-key')
  wrapper.unmount()
})

it('已有密钥可以留空使用；更换服务商会要求重新填写', async () => {
  getAiVideoSettings.mockResolvedValue({ ...config, configured: true, enabled: true })
  const wrapper = mount(TeacherAiSettingsView, options)
  await flushPromises()
  expect(wrapper.get('button[type=submit]').attributes('disabled')).toBeUndefined()
  testAiVideoSettings.mockResolvedValue({ message: '音视频请求已通过。' })
  const testButton = wrapper.findAll('button').find((b) => b.text() === '测试视频连接')
  await testButton.trigger('click'); await flushPromises()
  expect(testAiVideoSettings).toHaveBeenCalledWith(expect.objectContaining({ api_key: null }))
  expect(saveAiVideoSettings).not.toHaveBeenCalled()
  await wrapper.get('#ai-provider').setValue('gemini')
  expect(wrapper.get('#ai-base').element.value).toContain('googleapis.com')
  expect(wrapper.get('button[type=submit]').attributes('disabled')).toBeDefined()
  wrapper.unmount()
})

it('连接失败显示错误，仍可修改配置；删除密钥后更新状态', async () => {
  getAiVideoSettings.mockResolvedValueOnce({ ...config, configured: true, enabled: true }).mockResolvedValue(config)
  testAiVideoSettings.mockRejectedValue(new Error('密钥无效'))
  deleteAiVideoSettings.mockResolvedValue({ deleted: true })
  const wrapper = mount(TeacherAiSettingsView, options)
  await flushPromises()
  await wrapper.findAll('button').find((b) => b.text() === '测试视频连接').trigger('click')
  await flushPromises()
  expect(wrapper.get('[role=alert]').text()).toContain('密钥无效')
  await wrapper.findAll('button').find((b) => b.text().includes('删除已保存密钥')).trigger('click')
  await flushPromises()
  expect(deleteAiVideoSettings).toHaveBeenCalledOnce()
  expect(wrapper.text()).toContain('已删除密钥')
  wrapper.unmount()
})
