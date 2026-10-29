// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import ReviewerTasksView from './ReviewerTasksView.vue'
import * as api from '../api/reviewer'
vi.mock('../api/reviewer', () => ({ getMyReviewTasks: vi.fn(), openReviewAnswer: vi.fn(), downloadReviewMaterial: vi.fn(), submitReview: vi.fn(), reviseReview: vi.fn() }))
beforeEach(() => {
  vi.resetAllMocks()
  const task = { task_id: 1, assignment_title: '证明题', anonymous_token: 'XYZ', status: 'PENDING', materials: [], answer_url: '/answer', rubric_items: [{ id: 2, name: '正确性', max_score: 100 }] }
  api.getMyReviewTasks.mockResolvedValueOnce([task]).mockResolvedValue([{ ...task, status: 'IN_PROGRESS' }])
  api.openReviewAnswer.mockResolvedValue({ content: '<script>无身份的答案</script>', statement: '证明递推式' })
})
it('在线答案打开后可评分，内容不执行 HTML，不调用文件下载', async () => {
  const w = mount(ReviewerTasksView); await flushPromises()
  const button = w.findAll('button').find(b => b.text() === '打开匿名答案并开始评审')
  expect(button.element.disabled).toBe(false)
  await button.trigger('click'); await flushPromises()
  expect(api.openReviewAnswer).toHaveBeenCalledWith(1)
  expect(api.downloadReviewMaterial).not.toHaveBeenCalled()
  expect(w.get('[aria-label="匿名在线答案"]').text()).toContain('<script>无身份的答案</script>')
  expect(w.find('script').exists()).toBe(false)
  expect(w.get('fieldset').element.disabled).toBe(false)
  w.unmount()
})

const findButton = (w, text) => w.findAll('button').find((button) => button.text() === text)
const submittedTask = (canAmend = true) => ({ task_id: 7, assignment_title: '期末演示', anonymous_token: 'ANON',
  status: 'SUBMITTED', can_amend: canAmend, review_deadline: '2030-01-01T00:00:00Z', materials: [],
  rubric_items: [{ id: 2, name: '正确性', max_score: 100 }],
  review: { version: 1, rubric_scores: [{ rubric_item_id: 2, score: 88 }], comment: '首次评分。' } })

async function openSubmitted(task) {
  api.getMyReviewTasks.mockReset().mockImplementation(async (status) => status === 'SUBMITTED' ? [task] : [])
  const w = mount(ReviewerTasksView)
  await flushPromises()
  await findButton(w, '已提交').trigger('click')
  await flushPromises()
  return w
}

it('已提交评分可查看和修改，必须填写原因，保存时携带版本号', async () => {
  const task = submittedTask()
  const w = await openSubmitted(task)
  expect(w.get('fieldset').element.disabled).toBe(true)
  expect(w.get('.score-input input').element.value).toBe('88')
  await findButton(w, '修改评分').trigger('click')
  expect(w.get('fieldset').element.disabled).toBe(false)
  expect(findButton(w, '保存修改及原因').element.disabled).toBe(true)
  await w.get('.score-input input').setValue('95')
  await w.get('.review-form').trigger('submit')
  expect(api.reviseReview).not.toHaveBeenCalled()
  await w.get('textarea[placeholder^="例如"]').setValue('上一版误填，核对代码后更正。')
  api.reviseReview.mockImplementation(async () => {
    task.review = { version: 2, rubric_scores: [{ rubric_item_id: 2, score: 95 }], comment: '首次评分。' }
  })
  await w.get('.review-form').trigger('submit')
  await flushPromises()
  expect(api.reviseReview).toHaveBeenCalledWith(7, { expected_version: 1, reason: '上一版误填，核对代码后更正。',
    comment: '首次评分。', rubric_scores: [{ rubric_item_id: 2, score: 95 }] })
  expect(api.submitReview).not.toHaveBeenCalled()
  expect(w.text()).toContain('修改原因和前后记录已同步到教师端')
  expect(w.text()).toContain('v2')
  expect(w.get('fieldset').element.disabled).toBe(true)
  w.unmount()
})

it('保存失败保留填写内容，取消修改恢复已提交值', async () => {
  const w = await openSubmitted(submittedTask())
  await findButton(w, '修改评分').trigger('click')
  await w.get('.score-input input').setValue('95')
  await w.get('textarea[placeholder^="例如"]').setValue('核对后更正分数。')
  api.reviseReview.mockRejectedValue(new Error('评分已在其他页面修改，请刷新任务。'))
  await w.get('.review-form').trigger('submit')
  await flushPromises()
  expect(w.get('[role=alert]').text()).toContain('请刷新任务')
  expect(w.get('.score-input input').element.value).toBe('95')
  expect(w.get('textarea[placeholder^="例如"]').element.value).toBe('核对后更正分数。')
  await findButton(w, '取消修改').trigger('click')
  expect(w.get('.score-input input').element.value).toBe('88')
  expect(w.get('fieldset').element.disabled).toBe(true)
  w.unmount()
})

it('评审关闭后已提交任务只读，不显示修改入口', async () => {
  const w = await openSubmitted(submittedTask(false))
  expect(findButton(w, '修改评分')).toBeUndefined()
  expect(w.get('fieldset').element.disabled).toBe(true)
  expect(w.text()).toContain('当前评分只读')
  w.unmount()
})

it('停留在修改表单直到截止时，自动禁用分数和保存按钮', async () => {
  vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
  let w
  try {
    vi.setSystemTime(new Date('2026-10-28T10:00:00Z'))
    w = await openSubmitted({ ...submittedTask(), review_deadline: '2026-10-28T10:00:02Z' })
    await findButton(w, '修改评分').trigger('click')
    await w.get('textarea[placeholder^="例如"]').setValue('核对后更正分数。')
    expect(findButton(w, '保存修改及原因').element.disabled).toBe(false)
    await vi.advanceTimersByTimeAsync(2000)
    expect(w.get('fieldset').element.disabled).toBe(true)
    expect(findButton(w, '保存修改及原因').element.disabled).toBe(true)
  } finally {
    w?.unmount()
    vi.useRealTimers()
  }
})

it('首次提交后进入已提交列表，可继续打开修改入口', async () => {
  const task = { ...submittedTask(), status: 'IN_PROGRESS', review: null, can_amend: false }
  api.getMyReviewTasks.mockReset().mockImplementation(async () => [task])
  api.submitReview.mockImplementation(async () => Object.assign(task, submittedTask()))
  const w = mount(ReviewerTasksView)
  await flushPromises()
  await w.get('.score-input input').setValue('88')
  await w.get('textarea').setValue('首次评分。')
  await w.get('.review-form').trigger('submit')
  await flushPromises()
  expect(api.submitReview).toHaveBeenCalledWith(7, { rubric_scores: [{ rubric_item_id: 2, score: 88 }], comment: '首次评分。' })
  expect(api.getMyReviewTasks).toHaveBeenLastCalledWith('SUBMITTED')
  expect(findButton(w, '修改评分')).toBeDefined()
  expect(w.text()).not.toContain('不能修改')
  w.unmount()
})
