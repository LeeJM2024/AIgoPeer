// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import TextAiSettings from './TextAiSettings.vue'
import * as api from '../../api/ai'
vi.mock('../../api/ai', () => ({ getTextAiSettings: vi.fn(), saveTextAiSettings: vi.fn(), testTextAiSettings: vi.fn(), deleteTextAiSettings: vi.fn() }))
const config = { configured: false, enabled: false, base_url: 'https://api.deepseek.com', model: 'deepseek-flash', student_daily_limit: 30, allow_full_solution: false }
const open = () => mount(TextAiSettings, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
beforeEach(() => { vi.resetAllMocks(); api.getTextAiSettings.mockResolvedValue({ ...config }) })
it('老师保存密钥、配额和辅导策略，成功后清空密钥框', async () => {
  api.saveTextAiSettings.mockResolvedValue({ ...config, configured: true, enabled: true })
  const w = open(); await flushPromises()
  expect(w.get('button[type=submit]').element.disabled).toBe(true)
  await w.get('#text-ai-key').setValue('secret'); await w.get('#text-ai-limit').setValue('15'); await w.get('form').trigger('submit'); await flushPromises()
  expect(api.saveTextAiSettings).toHaveBeenCalledWith(expect.objectContaining({ api_key: 'secret', student_daily_limit: 15, allow_full_solution: false }))
  expect(w.get('#text-ai-key').element.value).toBe(''); w.unmount()
})
it('测试不保存；更换接口必须重新填密钥', async () => {
  api.getTextAiSettings.mockResolvedValue({ ...config, configured: true, enabled: true }); api.testTextAiSettings.mockResolvedValue({ message: '连接成功' })
  const w = open(); await flushPromises()
  await w.findAll('button').find(b => b.text() === '测试文字连接').trigger('click'); await flushPromises()
  expect(api.testTextAiSettings).toHaveBeenCalledWith(expect.objectContaining({ api_key: null })); expect(api.saveTextAiSettings).not.toHaveBeenCalled()
  await w.get('#text-ai-base').setValue('https://different.example/v1'); expect(w.get('button[type=submit]').element.disabled).toBe(true); w.unmount()
})
