// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { expect, it, vi } from 'vitest'
import TeacherAiHubView from './TeacherAiHubView.vue'
import { getAiVideoSettings } from '../../api/teacher'
const { route } = vi.hoisted(() => ({ route: { value: null } }))
vi.mock('vue-router', () => ({ useRoute: () => route.value, RouterLink: { template: '<a><slot /></a>' } }))
vi.mock('../../api/teacher', () => ({ getAiVideoSettings: vi.fn(), saveAiVideoSettings: vi.fn(), testAiVideoSettings: vi.fn(), deleteAiVideoSettings: vi.fn() }))
it('切换文字和视频配置时保留已加载表单，不重复请求', async () => {
  route.value = reactive({ query: { tab: 'video' } })
  getAiVideoSettings.mockResolvedValue({ configured: false, provider: 'qwen', base_url: 'https://example.com', model: 'test' })
  const wrapper = mount(TeacherAiHubView, { global: { stubs: { TextAiSettings: { template: '<div>文字配置</div>' } } } })
  await flushPromises()
  await wrapper.get('#ai-model').setValue('unsaved-model')
  route.value.query.tab = ''; await flushPromises()
  expect(wrapper.text()).toContain('文字配置')
  route.value.query.tab = 'video'; await flushPromises()
  expect(wrapper.get('#ai-model').element.value).toBe('unsaved-model')
  expect(getAiVideoSettings).toHaveBeenCalledOnce()
  wrapper.unmount()
})
