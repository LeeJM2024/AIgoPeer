// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import AuthExperience from './AuthExperience.vue'

const global = { stubs: {
  AlgorithmArtwork: true,
  RouterLink: { props:['to'], template:'<a :href="to"><slot /></a>' },
} }

it('真实表单位于独立列，算法海报不再包进重复宣传卡片', () => {
  const wrapper = mount(AuthExperience, { slots:{default:'<form aria-label="登录表单"><button>登录</button></form>'}, global })
  expect(wrapper.get('.auth-form-column form').attributes('aria-label')).toBe('登录表单')
  expect(wrapper.findAll('#poster-title span').map(item=>item.text())).toEqual(['写出解法','讲清思路'])
  expect(wrapper.find('algorithm-artwork-stub').exists()).toBe(true)
  expect(wrapper.find('.tour-picture').exists()).toBe(false)
  expect(wrapper.get('.auth-brand').attributes('href')).toBe('/login')
  expect(wrapper.get('.auth-brand img').attributes('alt')).toBe('华中科技大学 网络空间安全学院')
  wrapper.unmount()
})

it('课程登录保持统一入口，不提供学生自助注册', () => {
  const wrapper = mount(AuthExperience, {global})
  expect(wrapper.get('.auth-form-column').attributes('aria-label')).toBe('课程登录')
  expect(wrapper.text()).not.toContain('注册')
  expect(wrapper.find('a[href="/register"]').exists()).toBe(false)
  wrapper.unmount()
})
