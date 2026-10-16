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
  vi.useFakeTimers()
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
  vi.useRealTimers()
})

it('提供可访问的暂停和播放控制', async () => {
  const wrapper = open()
  await wrapper.vm.$nextTick()
  expect(wrapper.classes()).toContain('is-moving')
  await wrapper.get('button[aria-label="暂停演算"]').trigger('click')
  expect(wrapper.classes()).not.toContain('is-moving')
  expect(wrapper.get('button').attributes('aria-pressed')).toBe('true')
  await wrapper.get('button[aria-label="播放演算"]').trigger('click')
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
  expect(wrapper.find('[aria-label="播放演算"]').exists()).toBe(false)
  const before = wrapper.get('.algorithm-caption strong').text()
  await wrapper.get('[aria-label="下一步演算"]').trigger('click')
  expect(wrapper.get('.algorithm-caption strong').text()).not.toBe(before)
  await wrapper.get('[aria-label="重新演算"]').trigger('click')
  expect(wrapper.get('.algorithm-caption strong').text()).toBe(before)
  expect(wrapper.classes()).not.toContain('is-moving')
  wrapper.unmount()
  wrappers.pop()
  expect(disconnect).toHaveBeenCalledOnce()
  expect(preference.removeEventListener).toHaveBeenCalledWith('change', expect.any(Function))
})

it('原生算法图无需外部图片请求，仍提供静态结构与说明', () => {
  const wrapper = open({ controls: false })
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.get('svg[role=img]').attributes('aria-label')).toContain('归并排序')
  expect(wrapper.findAll('.merge-tile')).toHaveLength(4)
  expect(wrapper.find('button').exists()).toBe(false)
})

it('计时驱动真实演算，暂停不推进，手动步进同步高亮代码', async () => {
  const wrapper = open()
  await wrapper.vm.$nextTick()
  await vi.advanceTimersByTimeAsync(1200)
  expect(wrapper.get('.algorithm-caption strong').text()).toContain('拆成两个子问题')
  expect(wrapper.get('.code-active text').text()).toContain('mid =')
  await wrapper.get('[aria-label="暂停演算"]').trigger('click')
  const paused = wrapper.get('.algorithm-caption strong').text()
  await vi.advanceTimersByTimeAsync(5000)
  expect(wrapper.get('.algorithm-caption strong').text()).toBe(paused)
  await wrapper.get('[aria-label="下一步演算"]').trigger('click')
  expect(wrapper.get('.algorithm-caption strong').text()).not.toBe(paused)
})

it('演算完整结束后停止，重播恢复初始数组', async () => {
  const wrapper = open()
  await wrapper.vm.$nextTick()
  await vi.advanceTimersByTimeAsync(120000)
  expect(wrapper.get('.algorithm-caption strong').text()).toBe('归并完成：1、3、5、8')
  expect(wrapper.classes()).not.toContain('is-moving')
  expect(wrapper.get('[aria-label="下一步演算"]').attributes('disabled')).toBeDefined()
  await wrapper.get('[aria-label="重新演算"]').trigger('click')
  expect(wrapper.get('.algorithm-caption strong').text()).toBe('从无序数组开始')
  expect(wrapper.classes()).toContain('is-moving')
  wrapper.unmount()
  wrappers.pop()
  expect(vi.getTimerCount()).toBe(0)
})
