// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import VideoAnalysis from './VideoAnalysis.vue'
import { cancelVideoAnalysis, getAiVideoSettings, getVideoAnalyses, startVideoAnalysis } from '../../api/teacher'

vi.mock('../../api/teacher', () => ({ getAiVideoSettings: vi.fn(), getVideoAnalyses: vi.fn(), startVideoAnalysis: vi.fn(), cancelVideoAnalysis: vi.fn() }))
const options = { props: { submissionId: 45 }, global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } }
const record = (status) => ({ id: 1, status, provider: 'qwen', model: 'omni', created_at: '2026-10-29T00:00:00Z', progress_json: { completed_clips: 1, total_clips: 2 } })
beforeEach(() => { vi.resetAllMocks(); getAiVideoSettings.mockResolvedValue({ configured: true, enabled: true }); getVideoAnalyses.mockResolvedValue({ runs: [] }) })
afterEach(() => vi.useRealTimers())

it('未配置时引导教师填写密钥', async () => {
  getAiVideoSettings.mockResolvedValue({ configured: false, enabled: false })
  const wrapper = mount(VideoAnalysis, options)
  await flushPromises()
  expect(wrapper.text()).toContain('填写密钥并开启分析')
  expect(wrapper.get('button').attributes('disabled')).toBeDefined()
  wrapper.unmount()
})

it('展示评分建议，点击时间点发送原视频定位事件', async () => {
  getVideoAnalyses.mockResolvedValue({ runs: [{ ...record('SUCCEEDED'), result_json: {
    summary: '完整讲解归并排序', assessments: [{ rubric_item_id: 2, name: '正确性', suggested_score: '28', max_score: '30', confidence: .8, rationale: '步骤清楚', evidence: [{ start_seconds: 75, end_seconds: 90, description: '合并步骤' }] }],
  } }] })
  const wrapper = mount(VideoAnalysis, options)
  await flushPromises()
  expect(wrapper.text()).toContain('建议 28 / 30')
  await wrapper.get('.time-link').trigger('click')
  expect(wrapper.emitted('seek')).toEqual([[75]])
  wrapper.unmount()
})

it('创建后轮询进度，卸载后停止轮询', async () => {
  vi.useFakeTimers()
  startVideoAnalysis.mockResolvedValue({ run_id: 1 })
  const wrapper = mount(VideoAnalysis, options)
  await flushPromises()
  getVideoAnalyses.mockResolvedValue({ runs: [record('PROCESSING')] })
  await wrapper.findAll('button').find((b) => b.text() === '分析视频').trigger('click')
  await flushPromises()
  expect(startVideoAnalysis).toHaveBeenCalledWith(45, false)
  expect(wrapper.text()).toContain('1 / 2')
  await vi.advanceTimersByTimeAsync(3000)
  expect(getVideoAnalyses).toHaveBeenCalledTimes(3)
  wrapper.unmount()
  await vi.advanceTimersByTimeAsync(6000)
  expect(getVideoAnalyses).toHaveBeenCalledTimes(3)
})

it('可以停止当前分析并再次发起', async () => {
  getVideoAnalyses.mockResolvedValueOnce({ runs: [record('PROCESSING')] }).mockResolvedValue({ runs: [record('CANCELLED')] })
  cancelVideoAnalysis.mockResolvedValue({ cancelled: true })
  const wrapper = mount(VideoAnalysis, options)
  await flushPromises()
  await wrapper.findAll('button').find((b) => b.text() === '停止分析').trigger('click')
  await flushPromises()
  expect(cancelVideoAnalysis).toHaveBeenCalledWith(45, 1)
  expect(wrapper.text()).toContain('重新分析视频')
  wrapper.unmount()
})
