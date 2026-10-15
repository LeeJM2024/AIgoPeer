// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import AlgorithmArtwork from './AlgorithmArtwork.vue'

const wrappers = []
let intersect
let preference
let disconnect
function open(props = {}) {
  const wrapper = mount(AlgorithmArtwork, { props })
  wrappers.push(wrapper)
  return wrapper
}
beforeEach(() => {
  preference = { matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }
  vi.stubGlobal('matchMedia', vi.fn(() => preference))
  disconnect = vi.fn()
  vi.stubGlobal('IntersectionObserver', class {
    constructor(callback) { intersect = callback }
    observe() {}
    disconnect() { disconnect() }
  })
})
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  vi.unstubAllGlobals()
})

it('提供可访问的暂停和播放控制', async () => {
  const wrapper = open()
  expect(wrapper.classes()).toContain('is-moving')
  await wrapper.get('button[aria-label="暂停宣传动画"]').trigger('click')
  expect(wrapper.classes()).not.toContain('is-moving')
  expect(wrapper.get('button').attributes('aria-pressed')).toBe('true')
  await wrapper.get('button[aria-label="播放宣传动画"]').trigger('click')
  expect(wrapper.classes()).toContain('is-moving')
})

it('离开视口后暂停，切换页面可见性不会错误地恢复', async () => {
  const wrapper = open()
  intersect([{ isIntersecting: false }])
  await wrapper.vm.$nextTick()
  document.dispatchEvent(new Event('visibilitychange'))
  await wrapper.vm.$nextTick()
  expect(wrapper.classes()).not.toContain('is-moving')
  intersect([{ isIntersecting: true }])
  await wrapper.vm.$nextTick()
  expect(wrapper.classes()).toContain('is-moving')
})

it('尊重减少动态效果设置并清理监听', async () => {
  preference.matches = true
  const wrapper = open()
  await wrapper.vm.$nextTick()
  expect(wrapper.classes()).not.toContain('is-moving')
  expect(wrapper.find('button').exists()).toBe(false)
  wrapper.unmount()
  wrappers.pop()
  expect(disconnect).toHaveBeenCalledOnce()
  expect(preference.removeEventListener).toHaveBeenCalledWith('change', expect.any(Function))
})

it('图片加载失败仍保留有含义的算法结构', async () => {
  const wrapper = open({ controls: false })
  await wrapper.get('img').trigger('error')
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.get('svg[role=img]').attributes('aria-label')).toContain('二叉树')
  expect(wrapper.find('button').exists()).toBe(false)
})
