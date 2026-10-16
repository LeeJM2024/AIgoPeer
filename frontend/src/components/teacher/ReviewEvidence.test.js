// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ReviewEvidence from './ReviewEvidence.vue'

describe('复核依据', () => {
  it('保留零分，用评分项名称显示差异，缺失值不冒充零分', () => {
    const wrapper = mount(ReviewEvidence, { props: {
      rubricItems: [{ id: 7, name: '原理讲解' }],
      evidence: {
        rules_triggered: ['FOUR_VS_ONE_OUTLIER'],
        rubric_evidence: [{ rubric_item_id: 7, reviewer_score: 0, other_four_median: 20, max_score: 30 }],
        behavior_evidence: { duration_seconds: 0, comment_char_count: null },
      },
    } })
    expect(wrapper.findAll('tbody td').map((cell) => cell.text())).toEqual(['原理讲解', '0', '20', '30'])
    expect(wrapper.text()).toContain('评阅用时：0 秒 · 评语：— 字')
    expect(wrapper.text()).toContain('与其他四人相差较大')
  })

  it('回退结果不显示成可用的模型参考分，未知规则仍提示复核', () => {
    const wrapper = mount(ReviewEvidence, { props: { evidence: {
      rules_triggered: ['FUTURE_RULE'],
      rubric_evidence: [{ bayesian_score: 80, ci_lower: 70, ci_upper: 90 }],
      uncertainty_evidence: { posterior_available: false, fallback_reason: 'PANEL_TOO_SMALL' },
    } } })
    expect(wrapper.text()).toContain('本次参考分采用五人评分的中间值')
    expect(wrapper.text()).toContain('这次评分需要核对')
    expect(wrapper.text()).not.toContain('模型参考分')
    expect(wrapper.text()).not.toMatch(/FUTURE_RULE|undefined|null/)
  })

  it('旧记录和空记录都可以查看，说明文字作为文本处理', () => {
    const wrapper = mount(ReviewEvidence, { props: { evidence: { reason: '<script>alert(1)</script>' } } })
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.text()).toContain('<script>alert(1)</script>')
    const empty = mount(ReviewEvidence, { props: { evidence: null } })
    expect(empty.text()).toContain('请结合学生材料')
  })
})
