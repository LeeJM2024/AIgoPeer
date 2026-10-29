// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import ReviewEvidence from './ReviewEvidence.vue'

it('历史证据不再将短用时、短评语显示为风险理由，保留真实评分异常和客观记录', () => {
  const wrapper = mount(ReviewEvidence, { props: { evidence: {
    rules_triggered: ['SHORT_DURATION', 'SHORT_COMMENT', 'FOUR_VS_ONE_OUTLIER'],
    behavior_evidence: { duration_seconds: 5, comment_char_count: 2 },
  } } })
  expect(wrapper.findAll('.evidence-reasons li')).toHaveLength(1)
  expect(wrapper.text()).toContain('与其他四人相差较大')
  expect(wrapper.text()).not.toContain('评阅用时较短')
  expect(wrapper.text()).not.toContain('评语较短')
  expect(wrapper.text()).not.toContain('可能不足以说明评分理由')
  expect(wrapper.text()).toContain('评阅用时：5 秒')
  expect(wrapper.text()).toContain('评语：2 字')
  wrapper.unmount()
})
