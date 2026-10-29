// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import StudentSubjectiveSubmissionView from './StudentSubjectiveSubmissionView.vue'
import * as api from '../../api/student/subjective'

vi.mock('../../api/student/subjective', () => ({ getSubjective: vi.fn(), getSubjectiveHistory: vi.fn(), submitSubjective: vi.fn() }))
const problem = () => ({ id: 1, title: '归纳证明', type: 'PROOF', statement: '证明递推式正确。',
  status: 'PUBLISHED', submit_deadline: '2099-01-01T00:00:00Z', topics: [], rubric_items: [], current: null })
const mountView = () => mount(StudentSubjectiveSubmissionView, { props: { assignmentId: '1' }, global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
afterEach(() => { vi.useRealTimers() })
beforeEach(() => {
  vi.resetAllMocks()
  api.getSubjective.mockResolvedValue(problem())
  api.getSubjectiveHistory.mockResolvedValue({ items: [], total: 0, page: 1 })
  api.submitSubjective.mockResolvedValue({ submission_id: 1, version: 1 })
})
it('在线显示题面、证明题类型和答题入口', async () => {
  const w = mountView(); await flushPromises()
  expect(w.text()).toContain('证明题')
  expect(w.text()).toContain('证明递推式正确。')
  await w.get('textarea').setValue('基例成立，归纳假设成立时可推出下一项。')
  await w.get('form').trigger('submit'); await flushPromises()
  expect(api.submitSubjective).toHaveBeenCalledWith('1', '基例成立，归纳假设成立时可推出下一项。')
  expect(w.get('[role=status]').text()).toContain('保存为新版本')
  w.unmount()
})
it('截止后恢复已有答案且禁止新提交，历史文本不执行 HTML', async () => {
  api.getSubjective.mockResolvedValue({ ...problem(), submit_deadline: '2020-01-01', current: { content: '已提交内容', version: 2 } })
  api.getSubjectiveHistory.mockResolvedValue({ items: [{ id: 8, version: 1, content: '<script>bad()</script>', submitted_at: '2020-01-01' }], total: 1 })
  const w = mountView(); await flushPromises()
  expect(w.get('textarea').element.readOnly).toBe(true)
  expect(w.get('textarea').element.value).toBe('已提交内容')
  await w.findAll('button').find(b => b.text() === '查看答案 v1').trigger('click')
  expect(w.get('pre').text()).toBe('<script>bad()</script>')
  expect(w.find('script').exists()).toBe(false)
  await w.get('form').trigger('submit')
  expect(api.submitSubjective).not.toHaveBeenCalled()
  w.unmount()
})
it('提交失败保留答案并显示服务端错误', async () => {
  api.submitSubjective.mockRejectedValue(new Error('请移除姓名学号'))
  const w = mountView(); await flushPromises()
  await w.get('textarea').setValue('尚未提交的答案')
  await w.get('form').trigger('submit'); await flushPromises()
  expect(w.get('[role=alert]').text()).toContain('请移除姓名学号')
  expect(w.get('textarea').element.value).toBe('尚未提交的答案')
  w.unmount()
})
it('切换作业忽略旧请求，避免把上题答案显示在新题', async () => {
  let resolveOld
  api.getSubjective.mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve }))
  const w = mountView()
  await w.setProps({ assignmentId: '2' }); await flushPromises()
  resolveOld({ ...problem(), title: '不应出现的旧题', current: { content: '旧答案' } }); await flushPromises()
  expect(w.text()).not.toContain('不应出现的旧题')
  expect(w.get('textarea').element.value).not.toBe('旧答案')
  w.unmount()
})
it('页面停留到截止时间后自动转为只读', async () => {
  vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
  vi.setSystemTime(new Date('2030-01-01T00:00:00Z'))
  api.getSubjective.mockResolvedValue({ ...problem(), submit_deadline: '2030-01-01T00:00:02Z' })
  const w = mountView(); await flushPromises()
  expect(w.get('textarea').element.readOnly).toBe(false)
  await vi.advanceTimersByTimeAsync(3000)
  expect(w.get('textarea').element.readOnly).toBe(true)
  w.unmount()
})
it('提交已成功但刷新失败时保留输入并说明已保存', async () => {
  const w = mountView(); await flushPromises()
  await w.get('textarea').setValue('完整证明过程')
  api.getSubjective.mockRejectedValueOnce(new Error('连接暂时中断'))
  await w.get('form').trigger('submit'); await flushPromises()
  expect(w.text()).toContain('答案已提交成功，但刷新失败')
  expect(w.get('textarea').element.value).toBe('完整证明过程')
  w.unmount()
})
