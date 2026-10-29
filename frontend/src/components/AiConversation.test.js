// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import AiConversation from './AiConversation.vue'
import AiAnswer from './AiAnswer.vue'
import * as api from '../api/ai'
vi.mock('../api/ai', () => ({ askAi: vi.fn(), getAiHistory: vi.fn(), getStudentAiStatus: vi.fn(), getTextAiSettings: vi.fn() }))
const wrappers = []
const open = (props = {}) => { const w = mount(AiConversation, { props: { mode: 'PROGRAMMING', contextId: '8', ...props }, global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } }); wrappers.push(w); return w }
beforeEach(() => { vi.resetAllMocks(); api.getAiHistory.mockResolvedValue({ items: [] }); api.getStudentAiStatus.mockResolvedValue({ configured: true, enabled: true, student_daily_limit: 30 }); api.getTextAiSettings.mockResolvedValue({ configured: true, enabled: true }) })
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.useRealTimers() })

it('发送当前草稿、选中片段与对应提交，并保留追问对话 ID', async () => {
  api.askAi.mockImplementation(async (_mode, _id, p) => ({ id: 1, ...p, answer: '检查边界', status: 'SUCCEEDED', remaining_today: 29 }))
  const w = open({ sourceCode: 'int a;', selectedCode: 'a', submissionId: 7 }); await flushPromises()
  await w.findAll('button').find(b => b.text() === '解释代码').trigger('click'); await flushPromises()
  expect(api.askAi).toHaveBeenCalledWith('PROGRAMMING', '8', expect.objectContaining({ source_code: 'int a;', selected_code: 'a', submission_id: 7 }))
  const conversation = api.askAi.mock.calls[0][2].conversation_id
  await w.setProps({ sourceCode: 'int b;', selectedCode: '' }); await w.get('textarea').setValue('继续解释'); await w.get('form').trigger('submit'); await flushPromises()
  expect(api.askAi.mock.calls[1][2]).toEqual(expect.objectContaining({ conversation_id: conversation, source_code: 'int b;' }))
  expect(w.text()).toContain('今日剩余 29 次')
})
it('老师未启用时禁用输入，不发送请求', async () => {
  api.getStudentAiStatus.mockResolvedValue({ configured: false, enabled: false })
  const w = open(); await flushPromises()
  expect(w.text()).toContain('老师尚未开启')
  expect(w.get('textarea').element.disabled).toBe(true)
  expect(api.askAi).not.toHaveBeenCalled()
})
it('刷新后恢复正在处理的对话，轮询直至获得结果', async () => {
  vi.useFakeTimers()
  const item = { id: 5, conversation_id: 'saved', question: '复杂度', status: 'PROCESSING' }
  api.getAiHistory.mockResolvedValueOnce({ items: [item] }).mockResolvedValue({ items: [{ ...item, status: 'SUCCEEDED', answer: 'O(n)' }] })
  const w = open(); await flushPromises()
  expect(w.get('textarea').element.disabled).toBe(true)
  await vi.advanceTimersByTimeAsync(3000); await flushPromises()
  expect(w.text()).toContain('O(n)'); expect(w.get('textarea').element.disabled).toBe(false)
})
it('请求失败保留输入供修改重试，新对话生成新的 ID', async () => {
  api.askAi.mockRejectedValueOnce(new Error('模型暂不可用')).mockImplementation(async (_m, _i, p) => ({ ...p, id: 2, answer: '回答', status: 'SUCCEEDED' }))
  const w = open({ mode: 'KNOWLEDGE' }); await flushPromises()
  await w.get('textarea').setValue('请举例'); await w.get('form').trigger('submit'); await flushPromises()
  expect(w.get('[role=alert]').text()).toContain('模型暂不可用'); expect(w.get('textarea').element.value).toBe('请举例')
  const first = api.askAi.mock.calls[0][2].conversation_id
  await w.findAll('button').find(b => b.text() === '新对话').trigger('click')
  await w.get('textarea').setValue('另一个问题'); await w.get('form').trigger('submit'); await flushPromises()
  expect(api.askAi.mock.calls[1][2].conversation_id).not.toBe(first)
  expect(api.askAi.mock.calls[1][2]).not.toHaveProperty('source_code')
})
it('教师请求按所选班级发送统计建议', async () => {
  api.askAi.mockImplementation(async (_m, _i, p) => ({ ...p, id: 2, answer: '建议', status: 'SUCCEEDED' }))
  const w = open({ mode: 'TEACHING', contextId: '12' }); await flushPromises()
  await w.findAll('button').find(b => b.text() === '生成教学建议').trigger('click'); await flushPromises()
  expect(api.askAi).toHaveBeenCalledWith('TEACHING', '12', expect.objectContaining({ action: 'teaching' }))
})
it('AI 回答中的 HTML 作为文字呈现，代码块可复制', async () => {
  const writeText = vi.fn().mockResolvedValue()
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  const w = mount(AiAnswer, { props: { content: '# 解释\n<img src=x onerror=alert(1)>\n```cpp\nint x = 0;\n```\n**结束**' } }); wrappers.push(w)
  expect(w.find('img').exists()).toBe(false); expect(w.get('pre').text()).toBe('int x = 0;')
  await w.get('button').trigger('click'); await flushPromises(); expect(writeText).toHaveBeenCalledWith('int x = 0;')
  expect(w.text()).toContain('已复制')
})
it('正确渲染 Markdown 表格、行内公式和公式块', async () => {
  const w = mount(AiAnswer, { props: { content: '| 操作 | 复杂度 |\n| --- | --- |\n| 双层循环 | $\\Theta(n^2)$ |\n\n$$\nT(n)=2T(n/2)+n=\\Theta(n\\log n)\n$$' } }); wrappers.push(w)
  expect(w.find('table').exists()).toBe(true)
  expect(w.findAll('tbody tr')).toHaveLength(1)
  expect(w.find('.katex').exists()).toBe(true)
  expect(w.find('.ai-math-block .katex-display').exists()).toBe(true)
  expect(w.text()).not.toContain('$\\Theta')
})
