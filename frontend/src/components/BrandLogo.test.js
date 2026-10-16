// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import BrandLogo from './BrandLogo.vue'

it('全站统一使用用户提供的校院图片，保留图片描述与原始比例', () => {
  const wrapper = mount(BrandLogo)
  const image = wrapper.get('img')
  expect(image.attributes('src')).toContain('hust-cse-logo.png')
  expect(image.attributes('alt')).toBe('华中科技大学 网络空间安全学院')
  expect(image.attributes('width')).toBe('302')
  expect(image.attributes('height')).toBe('71')
  expect(wrapper.find('svg').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('AlgoPeer')
  wrapper.unmount()
})
