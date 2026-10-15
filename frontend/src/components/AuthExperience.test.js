// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import AuthExperience from './AuthExperience.vue'

it('工作台预览可手动切换，图片和说明保持对应', async () => {
  const wrapper = mount(AuthExperience, {
    props: { showcase: true },
    global: { stubs: {
      AlgorithmArtwork: true,
      RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
    } },
  })
  expect(wrapper.get('.tour-picture img').attributes('src')).toBe('/artwork/preview-teacher.jpg')
  await wrapper.findAll('.tour-controls button')[1].trigger('click')
  expect(wrapper.get('.tour-picture img').attributes('src')).toBe('/artwork/preview-code.jpg')
  expect(wrapper.get('.tour-copy h3').text()).toBe('把思路写进代码')
  expect(wrapper.findAll('.tour-controls button')[1].attributes('aria-pressed')).toBe('true')
  await wrapper.findAll('.tour-contact-sheet button')[2].trigger('click')
  expect(wrapper.get('.tour-picture img').attributes('src')).toBe('/artwork/preview-student.jpg')
  wrapper.unmount()
})
