// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import AuthExperience from './AuthExperience.vue'

const global = { stubs: {
  AlgorithmArtwork: true,
  RouterLink: { props:['to'], template:'<a :href="to"><slot /></a>' },
} }

it('真实表单位于独立列，算法海报不再包进重复宣传卡片', () => {
  const wrapper = mount(AuthExperience, { props:{showcase:true}, slots:{default:'<form aria-label="登录表单"><button>登录</button></form>'}, global })
  expect(wrapper.get('.auth-form-column form').attributes('aria-label')).toBe('登录表单')
  expect(wrapper.findAll('#poster-title span').map(item=>item.text())).toEqual(['写出解法','讲清思路'])
  expect(wrapper.find('algorithm-artwork-stub').exists()).toBe(true)
  expect(wrapper.find('.tour-picture').exists()).toBe(false)
  expect(wrapper.get('.auth-brand').attributes('href')).toBe('/login')
  expect(wrapper.get('.auth-brand img').attributes('alt')).toBe('华中科技大学 网络空间安全学院')
  wrapper.unmount()
})

it('注册保留相同视觉入口并提供返回登录链接', () => {
  const wrapper = mount(AuthExperience, {props:{showcase:false},global})
  expect(wrapper.classes()).toContain('auth-register')
  expect(wrapper.get('.auth-form-column').attributes('aria-label')).toBe('学生注册')
  expect(wrapper.get('.auth-footer a').attributes('href')).toBe('/login')
  wrapper.unmount()
})
