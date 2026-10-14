// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import ProjectSubmissionHistory from './ProjectSubmissionHistory.vue'
import * as api from '../../api/student/projectSubmissions'

vi.mock('../../api/student/projectSubmissions', () => ({ getProjectSubmissionHistory: vi.fn(), getMaterialCheck: vi.fn() }))
const record = (id, current = false, status = 'VALID') => ({ id, version: id, is_current: current, material_check_status: status, submitted_at: '2026-10-14T06:00:00Z' })
const result = (status = 'VALID', missing = []) => ({ status, missing_items: missing, warnings: [], checked_at: null })
const wrappers = []
const button = (w, text) => w.findAll('button').find((b) => b.text() === text)
async function open(props = {}) {
  const w = mount(ProjectSubmissionHistory, { props: { assignmentId: 10, ...props } })
  wrappers.push(w)
  await flushPromises()
  return w
}
beforeEach(() => {
  vi.resetAllMocks()
  api.getProjectSubmissionHistory.mockResolvedValue({ items: [record(7, true), record(6)], total: 7, page: 1 })
  api.getMaterialCheck.mockResolvedValue(result())
})
afterEach(() => { wrappers.splice(0).forEach((w) => w.unmount()); vi.useRealTimers() })

it('显示当前标记、按服务端页翻页；材料状态缺失不伪装通过', async () => {
  const w = await open()
  expect(w.get('tbody tr').text()).toContain('第 7 版当前版本')
  api.getProjectSubmissionHistory.mockResolvedValue({ items: [record(2, false, null), record(1, false, 'INVALID')], total: 7, page: 2 })
  await button(w, '下一页').trigger('click')
  await flushPromises()
  expect(api.getProjectSubmissionHistory).toHaveBeenLastCalledWith(10, 2, 5)
  expect(w.text()).toContain('第 2 / 2 页')
  expect(w.get('tbody tr').text()).toContain('暂无检查记录')
})

it('空历史不读取材料详情', async () => {
  api.getProjectSubmissionHistory.mockResolvedValue({ items: [], total: 0, page: 1 })
  const w = await open()
  expect(w.text()).toContain('暂无提交记录')
  expect(api.getMaterialCheck).not.toHaveBeenCalled()
})

it('分页失败保留上一页和记录，允许重试', async () => {
  const w = await open()
  api.getProjectSubmissionHistory.mockRejectedValueOnce(new Error('网络不可用'))
  await button(w, '下一页').trigger('click')
  await flushPromises()
  expect(w.text()).toContain('网络不可用')
  expect(w.text()).toContain('第 1 / 2 页')
  expect(w.get('tbody tr').text()).toContain('第 7 版')
  await button(w, '刷新提交历史').trigger('click')
  await flushPromises()
  expect(w.find('[role=alert]').exists()).toBe(false)
})

it('快速切换详情时旧响应不覆盖最后选择，提示按文本展示', async () => {
  let resolveOld
  api.getMaterialCheck.mockImplementation((id) => id === 7 ? new Promise((r) => { resolveOld = r })
    : Promise.resolve({ ...result('INVALID', ['VIDEO']), warnings: ['<script>bad()</script>'] }))
  const w = await open()
  await w.get('button[aria-label="查看第 7 版材料检查"]').trigger('click')
  await w.get('button[aria-label="查看第 6 版材料检查"]').trigger('click')
  await flushPromises()
  resolveOld(result())
  await flushPromises()
  expect(w.get('.history-detail').text()).toContain('第 6 版材料检查')
  expect(w.get('.history-detail').text()).toContain('缺失项：VIDEO')
  expect(w.get('.history-detail').text()).toContain('<script>bad()</script>')
  expect(w.find('.history-detail script').exists()).toBe(false)
})

it('旧版 PENDING 不自动轮询，手动刷新后读取最终结果', async () => {
  vi.useFakeTimers()
  api.getMaterialCheck.mockResolvedValueOnce(result('PENDING')).mockResolvedValue(result('INVALID', ['VIDEO']))
  const w = await open()
  await w.get('button[aria-label="查看第 6 版材料检查"]').trigger('click')
  await flushPromises()
  expect(w.get('.history-detail').text()).toContain('手动刷新读取结果')
  await vi.advanceTimersByTimeAsync(10000)
  expect(api.getMaterialCheck).toHaveBeenCalledTimes(1)
  await button(w, '刷新此版本结果').trigger('click')
  await flushPromises()
  expect(w.get('.history-detail').text()).toContain('缺失项：VIDEO')
  expect(api.getMaterialCheck).toHaveBeenCalledTimes(2)
})

it('详情失败可刷新重试，不改变列表和当前标记', async () => {
  api.getMaterialCheck.mockRejectedValueOnce(new Error('查询失败')).mockResolvedValue(result())
  const w = await open()
  await w.get('button[aria-label="查看第 6 版材料检查"]').trigger('click')
  await flushPromises()
  expect(w.get('[role=alert]').text()).toContain('查询失败')
  await button(w, '刷新此版本结果').trigger('click')
  await flushPromises()
  expect(w.get('.history-detail').text()).toContain('完整性检查通过')
  expect(w.get('tbody tr').text()).toContain('第 7 版当前版本')
})

it('新当前版本刷新第一页并更新标记，已选旧详情保持不变', async () => {
  const w = await open({ latestSubmission: { id: 7, version: 7 }, latestCheck: result('PENDING') })
  expect(w.get('tbody tr').text()).toContain('检查中')
  await w.get('button[aria-label="查看第 6 版材料检查"]').trigger('click')
  await flushPromises()
  await w.setProps({ latestCheck: result() })
  expect(w.get('tbody tr').text()).toContain('完整性检查通过')
  api.getProjectSubmissionHistory.mockResolvedValue({ items: [record(8, true), record(7)], total: 8, page: 1 })
  await w.setProps({ latestSubmission: { id: 8, version: 8 } })
  await flushPromises()
  expect(api.getProjectSubmissionHistory).toHaveBeenLastCalledWith(10, 1, 5)
  expect(w.get('tbody tr').text()).toContain('第 8 版当前版本')
  expect(w.get('.history-detail').text()).toContain('第 6 版材料检查')
})
